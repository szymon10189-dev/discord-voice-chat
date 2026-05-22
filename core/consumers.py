from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .message_payload import build_message_payload
from .models import Channel, Message
from .presence import is_user_online, user_connected, user_disconnected
from .services import user_has_server_access, user_is_blocked_on_server
from .voice_presence import (
    voice_channel_name_for_user,
    voice_join,
    voice_leave,
    voice_peer_list,
)


def _format_validation_error(exc: ValidationError) -> str:
    if hasattr(exc, "error_dict"):
        parts = [str(err) for errs in exc.error_dict.values() for err in errs]
        return "; ".join(parts) if parts else str(exc)
    if hasattr(exc, "messages"):
        return "; ".join(str(m) for m in exc.messages)
    return str(exc)


def _voice_peers_with_status(channel_id: int, exclude_user_id: int | None) -> list[dict]:
    peers = voice_peer_list(channel_id, exclude_user_id=exclude_user_id)
    for peer in peers:
        peer["is_online"] = is_user_online(peer["user_id"])
    return peers


class PresenceMixin:
    """Wspólna obsługa statusu online (zielony/czerwony) dla WebSocketów serwera."""

    presence_group: str

    @database_sync_to_async
    def _presence_connect(self) -> bool:
        return user_connected(self.user.pk)

    @database_sync_to_async
    def _presence_disconnect(self) -> bool:
        return user_disconnected(self.user.pk)

    async def _broadcast_presence(self, online: bool) -> None:
        if not hasattr(self, "presence_group"):
            return
        await self.channel_layer.group_send(
            self.presence_group,
            {
                "type": "presence.update",
                "payload": {
                    "type": "presence_update",
                    "user_id": self.user.pk,
                    "online": online,
                },
            },
        )

    async def presence_update(self, event):
        await self.send_json(event["payload"])


class ChatConsumer(PresenceMixin, AsyncJsonWebsocketConsumer):
    """Czat w kanale: tekst, moderacja (usuwanie przez broadcast osobno)."""

    async def connect(self):
        self.channel_id = int(self.scope["url_route"]["kwargs"]["channel_id"])
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close(code=4001)
            return

        if await self.fetch_channel() is None:
            await self.close(code=4003)
            return

        if await self.is_user_blocked():
            await self.close(code=4004)
            return

        self.group_name = f"chat_{self.channel_id}"
        self.presence_group = f"server_presence_{self.server_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add(self.presence_group, self.channel_name)
        await self.accept()

        if await self._presence_connect():
            await self._broadcast_presence(True)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            if await self._presence_disconnect():
                await self._broadcast_presence(False)
            if hasattr(self, "presence_group"):
                await self.channel_layer.group_discard(
                    self.presence_group,
                    self.channel_name,
                )
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get("type") != "chat_message":
            await self.send_json(
                {"type": "error", "message": "Nieobsługiwany typ wiadomości."},
            )
            return

        if await self.is_user_blocked():
            await self.send_json(
                {
                    "type": "error",
                    "message": "Jesteś zablokowany na tym serwerze i nie możesz pisać.",
                },
            )
            return

        text = (content.get("content") or "").strip()
        if not text:
            await self.send_json(
                {"type": "error", "message": "Treść wiadomości nie może być pusta."},
            )
            return

        try:
            payload = await self.persist_message(text)
        except ValidationError as exc:
            await self.send_json(
                {"type": "error", "message": _format_validation_error(exc)},
            )
            return

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.broadcast",
                "payload": {"type": "message", "message": payload},
            },
        )

    async def chat_broadcast(self, event):
        await self.send_json(event["payload"])

    async def chat_moderation(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def fetch_channel(self):
        try:
            ch = Channel.objects.select_related("server").get(pk=self.channel_id)
        except Channel.DoesNotExist:
            return None
        if ch.channel_type != Channel.ChannelType.TEXT:
            return None
        if not user_has_server_access(self.user, ch.server):
            return None
        self.server_id = ch.server_id
        return ch

    @database_sync_to_async
    def is_user_blocked(self) -> bool:
        ch = Channel.objects.select_related("server").get(pk=self.channel_id)
        return user_is_blocked_on_server(self.user, ch.server)

    @database_sync_to_async
    def persist_message(self, text: str) -> dict:
        ch = Channel.objects.get(pk=self.channel_id)
        user = get_user_model().objects.get(pk=self.user.pk)
        msg = Message(channel=ch, author=user, content=text)
        msg.full_clean()
        msg.save()
        return build_message_payload(msg)


class VoiceConsumer(PresenceMixin, AsyncJsonWebsocketConsumer):
    """Kanał głosowy: obecność użytkowników + przekazywanie sygnałów WebRTC."""

    async def connect(self):
        self.channel_id = int(self.scope["url_route"]["kwargs"]["channel_id"])
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close(code=4001)
            return

        ch = await self.fetch_voice_channel()
        if ch is None:
            await self.close(code=4003)
            return

        if await self.is_user_blocked():
            await self.close(code=4004)
            return

        self.server_id = ch.server_id
        self.group_name = f"voice_{self.channel_id}"
        self.presence_group = f"server_presence_{self.server_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add(self.presence_group, self.channel_name)
        await self.accept()

        if await self._presence_connect():
            await self._broadcast_presence(True)

        voice_join(
            self.channel_id,
            self.user.pk,
            channel_name=self.channel_name,
            username=self.user.username,
        )

        await self.send_json(
            {
                "type": "peer_list",
                "peers": _voice_peers_with_status(
                    self.channel_id,
                    exclude_user_id=self.user.pk,
                ),
                "you": {
                    "user_id": self.user.pk,
                    "username": self.user.username,
                    "is_online": True,
                },
            }
        )

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "voice.broadcast",
                "payload": {
                    "type": "user_joined",
                    "user": {
                        "user_id": self.user.pk,
                        "username": self.user.username,
                        "is_online": is_user_online(self.user.pk),
                    },
                    "exclude_channel": self.channel_name,
                },
            },
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            if await self._presence_disconnect():
                await self._broadcast_presence(False)
            voice_leave(self.channel_id, self.user.pk)
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "voice.broadcast",
                    "payload": {
                        "type": "user_left",
                        "user_id": self.user.pk,
                        "username": self.user.username,
                    },
                },
            )
            if hasattr(self, "presence_group"):
                await self.channel_layer.group_discard(
                    self.presence_group,
                    self.channel_name,
                )
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type")
        if msg_type == "signal":
            target_id = content.get("target_user_id")
            if not target_id:
                return
            target_name = voice_channel_name_for_user(
                self.channel_id,
                int(target_id),
            )
            if not target_name:
                return
            await self.channel_layer.send(
                target_name,
                {
                    "type": "voice.signal",
                    "payload": {
                        "type": "signal",
                        "from_user_id": self.user.pk,
                        "from_username": self.user.username,
                        "signal_type": content.get("signal_type"),
                        "data": content.get("data"),
                    },
                },
            )
            return

        await self.send_json(
            {"type": "error", "message": "Nieobsługiwany typ wiadomości."},
        )

    async def voice_broadcast(self, event):
        payload = event["payload"]
        if payload.get("exclude_channel") == self.channel_name:
            return
        await self.send_json(payload)

    async def voice_signal(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def fetch_voice_channel(self):
        try:
            ch = Channel.objects.select_related("server").get(pk=self.channel_id)
        except Channel.DoesNotExist:
            return None
        if ch.channel_type != Channel.ChannelType.VOICE:
            return None
        if not user_has_server_access(self.user, ch.server):
            return None
        return ch

    @database_sync_to_async
    def is_user_blocked(self) -> bool:
        ch = Channel.objects.select_related("server").get(pk=self.channel_id)
        return user_is_blocked_on_server(self.user, ch.server)
