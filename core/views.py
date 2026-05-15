from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseBadRequest, JsonResponse
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
from .dm_utils import get_or_create_direct_conversation, user_participates_in_conversation
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

    def get(self, request, user_id):
        msgs = list(
            DirectMessage.objects.filter(conversation=self.conversation)
            .select_related("author")
            .order_by("created_at")[:500],
        )
        return render(
            request,
            self.template_name,
            {
                "conversation": self.conversation,
                "other": self.other_user,
                "messages": msgs,
                "form": DirectMessageForm(),
                "conv_rows": _dm_inbox_rows(request.user),
            },
        )

    def post(self, request, user_id):
        form = DirectMessageForm(request.POST, request.FILES)
        if form.is_valid():
            dm = form.save(commit=False)
            dm.conversation = self.conversation
            dm.author = request.user
            dm.save()
            return redirect("core:dm_thread", user_id=self.other_user.pk)
        msgs = list(
            DirectMessage.objects.filter(conversation=self.conversation)
            .select_related("author")
            .order_by("created_at")[:500],
        )
        return render(
            request,
            self.template_name,
            {
                "conversation": self.conversation,
                "other": self.other_user,
                "messages": msgs,
                "form": form,
                "conv_rows": _dm_inbox_rows(request.user),
            },
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


class DashboardView(LoginRequiredMixin, View):
    """Layout jak Discord: lista kanałów + okno czatu."""

    template_name = "core/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        self.server = get_object_or_404(Server, pk=kwargs["server_id"])
        if not user_has_server_access(request.user, self.server):
            raise PermissionDenied("Nie masz dostępu do tego serwera.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, server_id, channel_id=None):
        server = self.server
        channels = Channel.objects.filter(server=server).order_by("name")
        channel = None
        messages_list: list[Message] = []
        if channel_id is not None:
            channel = get_object_or_404(Channel, pk=channel_id, server=server)
            messages_list = list(
                Message.objects.filter(channel=channel)
                .select_related("author")
                .order_by("created_at")[:500],
            )
        elif channels.exists():
            first = channels.first()
            return redirect(
                "core:dashboard_channel",
                server_id=server.id,
                channel_id=first.id,
            )

        ctx = self._build_context(request, channel, channels, messages_list)
        return render(request, self.template_name, ctx)

    def post(self, request, server_id, channel_id=None):
        server = self.server
        channels = Channel.objects.filter(server=server).order_by("name")
        channel = None
        if channel_id is not None:
            channel = get_object_or_404(Channel, pk=channel_id, server=server)

        if "create_channel" in request.POST:
            if not user_is_server_admin(request.user, server):
                raise PermissionDenied("Tylko administrator może tworzyć kanały.")
            form = ChannelCreateForm(request.POST)
            if form.is_valid():
                ch = form.save(commit=False)
                ch.server = server
                ch.save()
                messages.success(request, f"Utworzono kanał #{ch.name}.")
                return redirect(
                    "core:dashboard_channel",
                    server_id=server.id,
                    channel_id=ch.id,
                )
            messages_list: list[Message] = []
            if channel:
                messages_list = list(
                    Message.objects.filter(channel=channel)
                    .select_related("author")
                    .order_by("created_at")[:500],
                )
            ctx = self._build_context(
                request,
                channel,
                channels,
                messages_list,
                channel_form=form,
            )
            return render(request, self.template_name, ctx)

        return HttpResponseBadRequest("Nieobsługiwane żądanie.")

    def _build_context(
        self,
        request,
        channel,
        channels,
        messages_list,
        *,
        channel_form=None,
    ):
        server = self.server
        is_admin = user_is_server_admin(request.user, server)
        if channel_form is None:
            channel_form = ChannelCreateForm() if is_admin else None
        elif not is_admin:
            channel_form = None
        return {
            "server": server,
            "channels": channels,
            "active_channel": channel,
            "messages": messages_list,
            "is_server_admin": is_admin,
            "channel_form": channel_form,
            "can_moderate": user_can_moderate(request.user, server),
        }


class AppLoginView(LoginView):
    template_name = "core/login.html"
    form_class = LoginForm
    redirect_authenticated_user = True


class AppLogoutView(LogoutView):
    next_page = reverse_lazy("core:home")


class RegisterView(FormView):
    template_name = "core/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("core:login")

    def form_valid(self, form):
        user = form.save()
        from .bootstrap import add_user_to_default_server

        add_user_to_default_server(user)
        messages.success(
            self.request,
            "Konto zostało utworzone. Po zalogowaniu zobaczysz domyślny serwer i kanał #ogólny.",
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
