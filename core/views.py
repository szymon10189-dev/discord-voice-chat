import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseBadRequest, JsonResponse
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, TemplateView, UpdateView

from .forms import (
    ChannelCreateForm,
    DirectConversationStartForm,
    DirectMessageForm,
    LoginForm,
    ProfileForm,
    RegisterForm,
)
from .message_payload import build_message_payload
from .reactions import (
    attach_reactions_to_direct_messages,
    attach_reactions_to_messages,
    toggle_direct_message_reaction,
    toggle_message_reaction,
    validate_reaction_emoji,
)
from .dm_utils import get_or_create_direct_conversation, user_participates_in_conversation
from .presence import online_user_ids
from .reporting import create_user_report
from .search_utils import search_for_viewer, server_members_for_sidebar
from .voice_presence import voice_rosters_for_channel_ids
from .models import Channel, DirectConversation, DirectMessage, Message, Server, ServerBan
from .services import (
    moderator_can_block_user,
    user_can_moderate,
    user_has_server_access,
    user_is_blocked_on_server,
    user_is_server_admin,
    user_servers_qs,
)

User = get_user_model()

CHAT_UPLOAD_MAX_BYTES = 12 * 1024 * 1024


def _dm_inbox_rows(user):
    qs = (
        DirectConversation.objects.filter(Q(user_a=user) | Q(user_b=user))
        .annotate(last_message_at=Max("messages__created_at"))
        .order_by("-last_message_at", "-pk")
    )
    rows = []
    for conv in qs:
        other = conv.other_user(user)
        last_msg = (
            DirectMessage.objects.filter(conversation=conv)
            .order_by("-created_at")
            .select_related("author")
            .first()
        )
        rows.append({"conversation": conv, "other": other, "last": last_msg})
    return rows


class DirectMessageInboxView(LoginRequiredMixin, View):
    """Lista rozmów prywatnych + formularz rozpoczęcia po nazwie użytkownika."""

    template_name = "core/dm_inbox.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                "start_form": DirectConversationStartForm(),
                "conv_rows": _dm_inbox_rows(request.user),
            },
        )

    def post(self, request):
        start_form = DirectConversationStartForm(request.POST)
        if start_form.is_valid():
            username = start_form.cleaned_data["username"]
            other = User.objects.filter(username__iexact=username).first()
            if not other:
                messages.error(request, "Nie znaleziono użytkownika o tej nazwie.")
            elif other.pk == request.user.pk:
                messages.error(request, "Nie możesz pisać wiadomości do samego siebie.")
            else:
                get_or_create_direct_conversation(request.user, other)
                return redirect("core:dm_thread", user_id=other.pk)
        return render(
            request,
            self.template_name,
            {
                "start_form": start_form,
                "conv_rows": _dm_inbox_rows(request.user),
            },
        )


class DirectMessageThreadView(LoginRequiredMixin, View):
    """Wątek DM z wybranym użytkownikiem (tworzy rozmowę przy pierwszej wizycie)."""

    template_name = "core/dm_thread.html"

    def dispatch(self, request, *args, user_id, **kwargs):
        self.other_user = get_object_or_404(User, pk=user_id)
        if self.other_user.pk == request.user.pk:
            messages.error(request, "Nie możesz prowadzić rozmowy z samym sobą.")
            return redirect("core:dm_inbox")
        self.conversation = get_or_create_direct_conversation(
            request.user,
            self.other_user,
        )
        if not user_participates_in_conversation(request.user, self.conversation):
            raise PermissionDenied("Brak dostępu do tej rozmowy.")
        return super().dispatch(request, *args, user_id=user_id, **kwargs)

    def _dm_messages(self):
        return list(
            DirectMessage.objects.filter(conversation=self.conversation)
            .select_related("author")
            .order_by("created_at")[:500],
        )

    def _dm_context(self, request, msgs, form):
        if msgs:
            attach_reactions_to_direct_messages(msgs, request.user)
        return {
            "conversation": self.conversation,
            "other": self.other_user,
            "messages": msgs,
            "form": form,
            "conv_rows": _dm_inbox_rows(request.user),
            "online_user_ids": online_user_ids(),
        }

    def get(self, request, user_id):
        msgs = self._dm_messages()
        return render(
            request,
            self.template_name,
            self._dm_context(request, msgs, DirectMessageForm()),
        )

    def post(self, request, user_id):
        form = DirectMessageForm(request.POST, request.FILES)
        if form.is_valid():
            dm = form.save(commit=False)
            dm.conversation = self.conversation
            dm.author = request.user
            dm.save()
            return redirect("core:dm_thread", user_id=self.other_user.pk)
        msgs = self._dm_messages()
        return render(
            request,
            self.template_name,
            self._dm_context(request, msgs, form),
        )


class DirectMessageReactionToggleView(LoginRequiredMixin, View):
    """AJAX: przełącz reakcję emoji na wiadomości prywatnej."""

    def post(self, request, user_id, message_id, *args, **kwargs):
        other = get_object_or_404(User, pk=user_id)
        if other.pk == request.user.pk:
            return JsonResponse({"error": "Nieprawidłowa rozmowa."}, status=400)

        conversation = get_or_create_direct_conversation(request.user, other)
        if not user_participates_in_conversation(request.user, conversation):
            return JsonResponse({"error": "Brak dostępu do tej rozmowy."}, status=403)

        dm = get_object_or_404(
            DirectMessage,
            pk=message_id,
            conversation=conversation,
        )

        emoji_raw = ""
        if request.content_type and "application/json" in request.content_type:
            try:
                body = json.loads(request.body.decode("utf-8") or "{}")
                emoji_raw = body.get("emoji", "")
            except json.JSONDecodeError:
                return JsonResponse({"error": "Nieprawidłowy JSON."}, status=400)
        else:
            emoji_raw = request.POST.get("emoji", "")

        try:
            reactions = toggle_direct_message_reaction(dm, request.user, emoji_raw)
        except ValidationError as exc:
            return JsonResponse(
                {"error": _format_upload_validation_error(exc)},
                status=400,
            )

        return JsonResponse(
            {
                "ok": True,
                "message_id": message_id,
                "reactions": reactions,
            }
        )


def _upload_allowed(file) -> bool:
    from .message_payload import classify_attachment_kind

    ct = (getattr(file, "content_type", None) or "").lower()
    if ct.startswith("image/") or ct.startswith("audio/"):
        return True
    name = getattr(file, "name", "") or ""
    return classify_attachment_kind(name) in ("image", "audio")


def _format_upload_validation_error(exc: ValidationError) -> str:
    if hasattr(exc, "error_dict"):
        parts = [str(err) for errs in exc.error_dict.values() for err in errs]
        return "; ".join(parts) if parts else str(exc)
    if hasattr(exc, "messages"):
        return "; ".join(str(m) for m in exc.messages)
    return str(exc)


def _parse_report_payload(request) -> tuple[str, int | None]:
    reason = ""
    message_id = None
    if request.content_type and "application/json" in request.content_type:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValidationError("Nieprawidłowy JSON.") from exc
        reason = (body.get("reason") or "").strip()
        raw_mid = body.get("message_id")
        if raw_mid not in (None, ""):
            message_id = int(raw_mid)
    else:
        reason = (request.POST.get("reason") or "").strip()
        raw_mid = request.POST.get("message_id")
        if raw_mid:
            message_id = int(raw_mid)
    return reason, message_id


class ChatMessageUploadView(LoginRequiredMixin, View):
    """AJAX: obraz lub nagranie głosowe — zapis + broadcast do grupy WebSocket."""

    def post(self, request, channel_id, *args, **kwargs):
        channel = get_object_or_404(Channel, pk=channel_id)
        if not user_has_server_access(request.user, channel.server):
            return JsonResponse(
                {"error": "Brak dostępu do tego kanału."},
                status=403,
            )
        if user_is_blocked_on_server(request.user, channel.server):
            return JsonResponse(
                {"error": "Jesteś zablokowany na tym serwerze i nie możesz wysyłać wiadomości."},
                status=403,
            )

        upload = request.FILES.get("file")
        if not upload:
            return JsonResponse({"error": "Nie przesłano pliku."}, status=400)
        if upload.size > CHAT_UPLOAD_MAX_BYTES:
            return JsonResponse(
                {"error": "Plik jest za duży (maks. 12 MB)."},
                status=400,
            )
        if not _upload_allowed(upload):
            return JsonResponse(
                {"error": "Dozwolone są tylko obrazy i pliki audio."},
                status=400,
            )

        caption = (request.POST.get("content") or "").strip()
        msg = Message(
            channel=channel,
            author=request.user,
            content=caption,
            attachment=upload,
        )
        try:
            msg.save()
        except ValidationError as exc:
            return JsonResponse(
                {"error": _format_upload_validation_error(exc)},
                status=400,
            )

        payload = build_message_payload(msg)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{channel.id}",
            {
                "type": "chat.broadcast",
                "payload": {"type": "message", "message": payload},
            },
        )
        return JsonResponse({"ok": True, "message": payload})


class ChatMessageReactionToggleView(LoginRequiredMixin, View):
    """AJAX: przełącz reakcję emoji na wiadomości + broadcast WebSocket."""

    def post(self, request, channel_id, message_id, *args, **kwargs):
        channel = get_object_or_404(Channel, pk=channel_id)
        if not user_has_server_access(request.user, channel.server):
            return JsonResponse({"error": "Brak dostępu do tego kanału."}, status=403)
        if user_is_blocked_on_server(request.user, channel.server):
            return JsonResponse(
                {"error": "Jesteś zablokowany na tym serwerze."},
                status=403,
            )

        msg = get_object_or_404(Message, pk=message_id, channel=channel)

        emoji_raw = ""
        if request.content_type and "application/json" in request.content_type:
            try:
                body = json.loads(request.body.decode("utf-8") or "{}")
                emoji_raw = body.get("emoji", "")
            except json.JSONDecodeError:
                return JsonResponse({"error": "Nieprawidłowy JSON."}, status=400)
        else:
            emoji_raw = request.POST.get("emoji", "")

        try:
            reactions = toggle_message_reaction(msg, request.user, emoji_raw)
        except ValidationError as exc:
            return JsonResponse(
                {"error": _format_upload_validation_error(exc)},
                status=400,
            )

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{channel.id}",
            {
                "type": "chat.broadcast",
                "payload": {
                    "type": "reactions_updated",
                    "message_id": message_id,
                    "reactions": reactions,
                },
            },
        )
        return JsonResponse(
            {
                "ok": True,
                "message_id": message_id,
                "reactions": reactions,
            }
        )


class ChatMessageDeleteView(LoginRequiredMixin, View):
    """AJAX: usuń wiadomość (Moderator / Admin) + broadcast WebSocket."""

    def post(self, request, channel_id, message_id, *args, **kwargs):
        channel = get_object_or_404(Channel, pk=channel_id)
        msg = get_object_or_404(Message, pk=message_id, channel=channel)
        if not user_can_moderate(request.user, channel.server):
            return JsonResponse({"error": "Brak uprawnień do moderacji."}, status=403)
        msg.delete()
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{channel.id}",
            {
                "type": "chat.moderation",
                "payload": {"type": "message_deleted", "message_id": message_id},
            },
        )
        return JsonResponse({"ok": True, "message_id": message_id})


class ServerUserBlockView(LoginRequiredMixin, View):
    """AJAX: zablokuj użytkownika na serwerze."""

    def post(self, request, server_id, user_id, *args, **kwargs):
        server = get_object_or_404(Server, pk=server_id)
        target = get_object_or_404(User, pk=user_id)
        if not user_can_moderate(request.user, server):
            return JsonResponse({"error": "Brak uprawnień do moderacji."}, status=403)
        if not moderator_can_block_user(request.user, server, target):
            return JsonResponse(
                {"error": "Nie możesz zablokować tego użytkownika."},
                status=400,
            )
        ServerBan.objects.get_or_create(
            server=server,
            blocked_user=target,
            defaults={"created_by": request.user},
        )
        return JsonResponse({"ok": True, "user_id": user_id})


class ServerUserUnblockView(LoginRequiredMixin, View):
    """AJAX: odblokuj użytkownika na serwerze."""

    def post(self, request, server_id, user_id, *args, **kwargs):
        server = get_object_or_404(Server, pk=server_id)
        target = get_object_or_404(User, pk=user_id)
        if not user_can_moderate(request.user, server):
            return JsonResponse({"error": "Brak uprawnień do moderacji."}, status=403)
        ServerBan.objects.filter(server=server, blocked_user=target).delete()
        return JsonResponse({"ok": True, "user_id": user_id})


class ServerUserReportView(LoginRequiredMixin, View):
    """AJAX: zgłoś użytkownika na serwerze (widoczne w panelu admina)."""

    def post(self, request, server_id, user_id, *args, **kwargs):
        server = get_object_or_404(Server, pk=server_id)
        target = get_object_or_404(User, pk=user_id)

        if not user_has_server_access(request.user, server):
            return JsonResponse({"error": "Brak dostępu do tego serwera."}, status=403)

        try:
            reason, message_id = _parse_report_payload(request)
        except (ValidationError, ValueError, TypeError) as exc:
            return JsonResponse(
                {"error": _format_upload_validation_error(exc) if isinstance(exc, ValidationError) else "Nieprawidłowe dane zgłoszenia."},
                status=400,
            )

        message = None
        if message_id is not None:
            message = get_object_or_404(Message, pk=message_id, channel__server=server)

        try:
            report = create_user_report(
                reporter=request.user,
                reported_user=target,
                reason=reason,
                server=server,
                message=message,
            )
        except ValidationError as exc:
            return JsonResponse(
                {"error": _format_upload_validation_error(exc)},
                status=400,
            )

        return JsonResponse(
            {
                "ok": True,
                "report_id": report.pk,
                "reported_user_id": target.pk,
            }
        )


class DirectUserReportView(LoginRequiredMixin, View):
    """AJAX: zgłoś użytkownika z rozmowy DM."""

    def post(self, request, user_id, *args, **kwargs):
        other = get_object_or_404(User, pk=user_id)
        if other.pk == request.user.pk:
            return JsonResponse({"error": "Nie możesz zgłosić samego siebie."}, status=400)

        conversation = get_or_create_direct_conversation(request.user, other)
        if not user_participates_in_conversation(request.user, conversation):
            return JsonResponse({"error": "Brak dostępu do tej rozmowy."}, status=403)

        try:
            reason, _message_id = _parse_report_payload(request)
        except (ValidationError, ValueError, TypeError) as exc:
            return JsonResponse(
                {"error": _format_upload_validation_error(exc) if isinstance(exc, ValidationError) else "Nieprawidłowe dane zgłoszenia."},
                status=400,
            )

        try:
            report = create_user_report(
                reporter=request.user,
                reported_user=other,
                reason=reason,
                server=None,
                message=None,
            )
        except ValidationError as exc:
            return JsonResponse(
                {"error": _format_upload_validation_error(exc)},
                status=400,
            )

        return JsonResponse(
            {
                "ok": True,
                "report_id": report.pk,
                "reported_user_id": other.pk,
            }
        )


class HomeView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        if user.is_authenticated:
            ctx["user_servers"] = user_servers_qs(user)
        else:
            ctx["user_servers"] = Server.objects.none()
        return ctx


def _server_channel_lists(server):
    qs = Channel.objects.filter(server=server).order_by("channel_type", "name")
    return {
        "text_channels": qs.filter(channel_type=Channel.ChannelType.TEXT),
        "voice_channels": qs.filter(channel_type=Channel.ChannelType.VOICE),
    }


def _voice_rosters_for_lists(channel_lists) -> dict:
    voice_ids = [ch.id for ch in channel_lists["voice_channels"]]
    return voice_rosters_for_channel_ids(voice_ids)


def _admin_channel_forms(is_admin, text_form=None, voice_form=None):
    if not is_admin:
        return None, None
    if text_form is None:
        text_form = ChannelCreateForm(channel_type=Channel.ChannelType.TEXT)
    if voice_form is None:
        voice_form = ChannelCreateForm(channel_type=Channel.ChannelType.VOICE)
    return text_form, voice_form


class ServerChannelAccessMixin:
    def dispatch(self, request, *args, **kwargs):
        self.server = get_object_or_404(Server, pk=kwargs["server_id"])
        if not user_has_server_access(request.user, self.server):
            raise PermissionDenied("Nie masz dostępu do tego serwera.")
        return super().dispatch(request, *args, **kwargs)

    def _try_create_channel(self, request, *, create_key: str, channel_type: str):
        if create_key not in request.POST:
            return None
        if not user_is_server_admin(request.user, self.server):
            raise PermissionDenied("Tylko administrator może tworzyć kanały.")
        form = ChannelCreateForm(request.POST, channel_type=channel_type)
        if form.is_valid():
            ch = form.save(commit=False)
            ch.server = self.server
            ch.channel_type = channel_type
            ch.save()
            label = "głosowy" if channel_type == Channel.ChannelType.VOICE else "tekstowy"
            messages.success(request, f"Utworzono kanał {label}: {ch.name}.")
            if ch.is_voice:
                return redirect(
                    "core:voice_channel",
                    server_id=self.server.id,
                    voice_channel_id=ch.id,
                )
            return redirect(
                "core:dashboard_channel",
                server_id=self.server.id,
                channel_id=ch.id,
            )
        return form


class DashboardView(LoginRequiredMixin, ServerChannelAccessMixin, View):
    template_name = "core/dashboard.html"

    def get(self, request, server_id, channel_id=None):
        channel_lists = _server_channel_lists(self.server)
        channel = None
        messages_list: list[Message] = []
        if channel_id is not None:
            raw = get_object_or_404(Channel, pk=channel_id, server=self.server)
            if raw.is_voice:
                return redirect(
                    "core:voice_channel",
                    server_id=self.server.id,
                    voice_channel_id=raw.id,
                )
            channel = raw
            messages_list = list(
                Message.objects.filter(channel=channel)
                .select_related("author")
                .order_by("created_at")[:500],
            )
        elif channel_lists["text_channels"].exists():
            first = channel_lists["text_channels"].first()
            return redirect(
                "core:dashboard_channel",
                server_id=self.server.id,
                channel_id=first.id,
            )

        ctx = self._build_context(request, channel, channel_lists, messages_list)
        return render(request, self.template_name, ctx)

    def post(self, request, server_id, channel_id=None):
        channel_lists = _server_channel_lists(self.server)
        channel = None
        messages_list: list[Message] = []
        if channel_id is not None:
            raw = get_object_or_404(Channel, pk=channel_id, server=self.server)
            if raw.is_voice:
                return redirect(
                    "core:voice_channel",
                    server_id=self.server.id,
                    voice_channel_id=raw.id,
                )
            channel = raw
            messages_list = list(
                Message.objects.filter(channel=channel)
                .select_related("author")
                .order_by("created_at")[:500],
            )

        text_form = self._try_create_channel(
            request,
            create_key="create_text_channel",
            channel_type=Channel.ChannelType.TEXT,
        )
        if text_form is not None and not isinstance(text_form, ChannelCreateForm):
            return text_form

        voice_form = self._try_create_channel(
            request,
            create_key="create_voice_channel",
            channel_type=Channel.ChannelType.VOICE,
        )
        if text_form is None and voice_form is None:
            return HttpResponseBadRequest("Nieobsługiwane żądanie.")
        if voice_form is not None and not isinstance(voice_form, ChannelCreateForm):
            return voice_form

        ctx = self._build_context(
            request,
            channel,
            channel_lists,
            messages_list,
            text_form=text_form if isinstance(text_form, ChannelCreateForm) else None,
            voice_form=voice_form if isinstance(voice_form, ChannelCreateForm) else None,
        )
        return render(request, self.template_name, ctx)

    def _build_context(
        self,
        request,
        channel,
        channel_lists,
        messages_list,
        *,
        text_form=None,
        voice_form=None,
    ):
        is_admin = user_is_server_admin(request.user, self.server)
        text_form, voice_form = _admin_channel_forms(is_admin, text_form, voice_form)
        if messages_list:
            attach_reactions_to_messages(messages_list, request.user)

        return {
            "server": self.server,
            "text_channels": channel_lists["text_channels"],
            "voice_channels": channel_lists["voice_channels"],
            "active_channel": channel,
            "active_voice_channel": None,
            "messages": messages_list,
            "is_server_admin": is_admin,
            "text_channel_form": text_form,
            "voice_channel_form": voice_form,
            "can_moderate": user_can_moderate(request.user, self.server),
            "online_user_ids": online_user_ids(),
            "server_members": server_members_for_sidebar(self.server),
            "voice_rosters": _voice_rosters_for_lists(channel_lists),
        }


class VoiceChannelView(LoginRequiredMixin, ServerChannelAccessMixin, View):
    template_name = "core/voice_channel.html"

    def get(self, request, server_id, voice_channel_id):
        voice_channel = get_object_or_404(
            Channel,
            pk=voice_channel_id,
            server=self.server,
            channel_type=Channel.ChannelType.VOICE,
        )
        channel_lists = _server_channel_lists(self.server)
        return render(
            request,
            self.template_name,
            self._build_context(request, voice_channel, channel_lists),
        )

    def post(self, request, server_id, voice_channel_id):
        voice_channel = get_object_or_404(
            Channel,
            pk=voice_channel_id,
            server=self.server,
            channel_type=Channel.ChannelType.VOICE,
        )
        channel_lists = _server_channel_lists(self.server)

        text_form = self._try_create_channel(
            request,
            create_key="create_text_channel",
            channel_type=Channel.ChannelType.TEXT,
        )
        if text_form is not None and not isinstance(text_form, ChannelCreateForm):
            return text_form

        voice_form = self._try_create_channel(
            request,
            create_key="create_voice_channel",
            channel_type=Channel.ChannelType.VOICE,
        )
        if text_form is None and voice_form is None:
            return HttpResponseBadRequest("Nieobsługiwane żądanie.")
        if voice_form is not None and not isinstance(voice_form, ChannelCreateForm):
            return voice_form

        return render(
            request,
            self.template_name,
            self._build_context(
                request,
                voice_channel,
                channel_lists,
                text_form=text_form if isinstance(text_form, ChannelCreateForm) else None,
                voice_form=voice_form if isinstance(voice_form, ChannelCreateForm) else None,
            ),
        )

    def _build_context(
        self,
        request,
        voice_channel,
        channel_lists,
        *,
        text_form=None,
        voice_form=None,
    ):
        is_admin = user_is_server_admin(request.user, self.server)
        text_form, voice_form = _admin_channel_forms(is_admin, text_form, voice_form)
        return {
            "server": self.server,
            "text_channels": channel_lists["text_channels"],
            "voice_channels": channel_lists["voice_channels"],
            "active_channel": None,
            "active_voice_channel": voice_channel,
            "is_server_admin": is_admin,
            "text_channel_form": text_form,
            "voice_channel_form": voice_form,
            "online_user_ids": online_user_ids(),
            "server_members": server_members_for_sidebar(self.server),
            "voice_rosters": _voice_rosters_for_lists(channel_lists),
        }


class SearchView(LoginRequiredMixin, View):
    """Globalne wyszukiwanie kanałów i użytkowników na serwerach użytkownika."""

    template_name = "core/search.html"

    def get(self, request):
        query = (request.GET.get("q") or "").strip()
        results = search_for_viewer(request.user, query)
        return render(
            request,
            self.template_name,
            {
                **results,
                "online_user_ids": online_user_ids(),
            },
        )


class AppLoginView(LoginView):
    template_name = "core/login.html"
    form_class = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        from .bootstrap import get_default_dashboard_redirect_url

        return get_default_dashboard_redirect_url(self.request.user)


class AppLogoutView(LogoutView):
    next_page = reverse_lazy("core:home")


class RegisterView(FormView):
    template_name = "core/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("core:login")

    def form_valid(self, form):
        from .bootstrap import add_user_to_default_server

        try:
            with transaction.atomic():
                user = form.save()
                add_user_to_default_server(user)
        except IntegrityError:
            form.add_error(
                "username",
                "Ta nazwa użytkownika jest już zajęta. Wybierz inną.",
            )
            return self.form_invalid(form)

        messages.success(
            self.request,
            "Konto utworzone. Zaloguj się — trafisz na serwer główny z kanałem #ogólny i ogólny-głos.",
        )
        return super().form_valid(form)


class ProfileEditView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = "core/profile_edit.html"
    success_url = reverse_lazy("core:profile_edit")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Profil został zapisany.")
        return super().form_valid(form)


def page_not_found_view(request, exception):
    """Niestandardowa strona 404 (szablon 404.html + GIF)."""
    return render(request, "404.html", status=404)
