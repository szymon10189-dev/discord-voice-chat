from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    def __str__(self) -> str:
        return self.username


class Server(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_servers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class ServerRole(models.Model):
    """Rola w obrębie serwera: Admin, Moderator lub User."""

    class RoleKind(models.TextChoices):
        ADMIN = "admin", "Admin"
        MODERATOR = "moderator", "Moderator"
        USER = "user", "User"

    server = models.ForeignKey(
        Server,
        on_delete=models.CASCADE,
        related_name="roles",
    )
    name = models.CharField(max_length=64)
    kind = models.CharField(
        max_length=20,
        choices=RoleKind.choices,
        default=RoleKind.USER,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["server", "kind"],
                name="core_serverrole_unique_kind_per_server",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.server.name} — {self.get_kind_display()}"


class ServerMember(models.Model):
    """Członkostwo użytkownika na serwerze z przypisaną rolą."""

    server = models.ForeignKey(
        Server,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="server_memberships",
    )
    role = models.ForeignKey(
        ServerRole,
        on_delete=models.PROTECT,
        related_name="members",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["server", "user"],
                name="core_servermember_unique_user_per_server",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.server}"


class ServerBan(models.Model):
    """Blokada użytkownika na serwerze (nie może pisać na kanałach)."""

    server = models.ForeignKey(
        Server,
        on_delete=models.CASCADE,
        related_name="bans",
    )
    blocked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="server_bans",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="server_bans_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["server", "blocked_user"],
                name="core_serverban_unique_blocked_per_server",
            ),
        ]

    def __str__(self) -> str:
        return f"Ban {self.blocked_user} @ {self.server}"


class UserReport(models.Model):
    """Zgłoszenie użytkownika przez innego użytkownika (widoczne w panelu admina)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Oczekuje"
        REVIEWED = "reviewed", "Rozpatrzone"
        DISMISSED = "dismissed", "Odrzucone"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submitted_reports",
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_reports",
    )
    server = models.ForeignKey(
        Server,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_reports",
    )
    message = models.ForeignKey(
        "Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_reports",
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Zgłoszenie użytkownika"
        verbose_name_plural = "Zgłoszenia użytkowników"

    def __str__(self) -> str:
        return f"Zgłoszenie: {self.reported_user} (przez {self.reporter})"


class Channel(models.Model):
    class ChannelType(models.TextChoices):
        TEXT = "text", "Tekstowy"
        VOICE = "voice", "Głosowy"

    server = models.ForeignKey(
        Server,
        on_delete=models.CASCADE,
        related_name="channels",
    )
    name = models.CharField(max_length=255)
    channel_type = models.CharField(
        max_length=10,
        choices=ChannelType.choices,
        default=ChannelType.TEXT,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["server", "name", "channel_type"],
                name="core_channel_unique_name_per_type",
            ),
        ]
        ordering = ["channel_type", "name"]

    @property
    def is_voice(self) -> bool:
        return self.channel_type == self.ChannelType.VOICE

    @property
    def is_text(self) -> bool:
        return self.channel_type == self.ChannelType.TEXT

    def __str__(self) -> str:
        prefix = "🔊" if self.is_voice else "#"
        return f"{prefix}{self.name}"


class Message(models.Model):
    """Wiadomość tekstowa i/lub z załącznikiem (dowolny plik)."""

    channel = models.ForeignKey(
        Channel,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    content = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to="message_attachments/",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def clean(self) -> None:
        super().clean()
        if not (self.content or "").strip() and not self.attachment:
            raise ValidationError(
                {"content": "Podaj treść wiadomości lub załącz plik."}
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def attachment_display_kind(self) -> str:
        if not self.attachment:
            return "none"
        from .message_payload import classify_attachment_kind

        return classify_attachment_kind(self.attachment.name)

    def __str__(self) -> str:
        preview = (self.content or "")[:40] or "(załącznik)"
        return f"{self.author}: {preview}"


class MessageReaction(models.Model):
    """Reakcja emoji użytkownika na wiadomość w kanale (toggle: ten sam emoji usuwa)."""

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="reactions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_reactions",
    )
    emoji = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["message", "user", "emoji"],
                name="core_messagereaction_unique_per_user_emoji",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.emoji} on msg {self.message_id} by {self.user_id}"


class DirectConversation(models.Model):
    """Rozmowa 1:1 — para użytkowników jest unikalna (user_a ma zawsze mniejsze id)."""

    user_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dm_conversations_as_a",
    )
    user_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dm_conversations_as_b",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_a", "user_b"],
                name="core_directconversation_unique_pair",
            ),
            models.CheckConstraint(
                condition=models.Q(user_a_id__lt=models.F("user_b_id")),
                name="core_directconversation_user_order",
            ),
        ]

    def other_user(self, viewer):
        if viewer.pk == self.user_a_id:
            return self.user_b
        if viewer.pk == self.user_b_id:
            return self.user_a
        raise ValueError("viewer not in conversation")

    def __str__(self) -> str:
        return f"DM {self.user_a} ↔ {self.user_b}"


class DirectMessage(models.Model):
    """Wiadomość prywatna w obrębie rozmowy 1:1."""

    conversation = models.ForeignKey(
        DirectConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_direct_messages",
    )
    content = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to="dm_attachments/",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def clean(self) -> None:
        super().clean()
        if not (self.content or "").strip() and not self.attachment:
            raise ValidationError(
                {"content": "Podaj treść wiadomości lub załącz plik."},
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def attachment_display_kind(self) -> str:
        if not self.attachment:
            return "none"
        from .message_payload import classify_attachment_kind

        return classify_attachment_kind(self.attachment.name)

    def __str__(self) -> str:
        preview = (self.content or "")[:40] or "(załącznik)"
        return f"DM {self.author}: {preview}"


class DirectMessageReaction(models.Model):
    """Reakcja emoji użytkownika na wiadomość prywatną (toggle)."""

    message = models.ForeignKey(
        DirectMessage,
        on_delete=models.CASCADE,
        related_name="reactions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="direct_message_reactions",
    )
    emoji = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["message", "user", "emoji"],
                name="core_directmessagereaction_unique_per_user_emoji",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.emoji} on DM {self.message_id} by {self.user_id}"
