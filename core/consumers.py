from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .message_payload import build_message_payload
from .models import Channel, Message
from .services import user_has_server_access, user_is_blocked_on_server


def _format_validation_error(exc: ValidationError) -> str:
    if hasattr(exc, "error_dict"):
        parts = [str(err) for errs in exc.error_dict.values() for err in errs]
        return "; ".join(parts) if parts else str(exc)
    if hasattr(exc, "messages"):
        return "; ".join(str(m) for m in exc.messages)
    return str(exc)


class ChatConsumer(AsyncJsonWebsocketConsumer):
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
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
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
        if not user_has_server_access(self.user, ch.server):
            return None
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
