from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Channel,
    DirectConversation,
    DirectMessage,
    DirectMessageReaction,
    Message,
    MessageReaction,
    Server,
    ServerBan,
    ServerMember,
    ServerRole,
    User,
    UserReport,
)


@admin.register(UserReport)
class UserReportAdmin(admin.ModelAdmin):
    list_display = (
        "reported_user",
        "reporter",
        "server",
        "status",
        "created_at",
        "reason_preview",
    )
    list_filter = ("status", "server", "created_at")
    search_fields = (
        "reported_user__username",
        "reporter__username",
        "reason",
        "admin_note",
    )
    list_select_related = ("reported_user", "reporter", "server", "message")
    readonly_fields = (
        "reporter",
        "reported_user",
        "server",
        "message",
        "reason",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            "Zgłoszenie",
            {
                "fields": (
                    "reported_user",
                    "reporter",
                    "server",
                    "message",
                    "reason",
                    "status",
                    "admin_note",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    @admin.display(description="Powód")
    def reason_preview(self, obj: UserReport) -> str:
        text = (obj.reason or "").strip()
        return text[:100] + ("…" if len(text) > 100 else "")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Profil", {"fields": ("avatar",)}),
    )
    list_display = ("username", "email", "first_name", "last_name", "is_staff")
    list_filter = ("is_staff", "is_superuser", "is_active")


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "created_at")
    search_fields = ("name",)


@admin.register(ServerRole)
class ServerRoleAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "server")
    list_filter = ("kind",)


@admin.register(ServerMember)
class ServerMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "server", "role")
    list_filter = ("server", "role__kind")


@admin.register(ServerBan)
class ServerBanAdmin(admin.ModelAdmin):
    list_display = ("blocked_user", "server", "created_by", "created_at")
    list_filter = ("server",)


@admin.register(DirectConversation)
class DirectConversationAdmin(admin.ModelAdmin):
    list_display = ("user_a", "user_b", "created_at")


@admin.register(DirectMessageReaction)
class DirectMessageReactionAdmin(admin.ModelAdmin):
    list_display = ("emoji", "message", "user", "created_at")
    list_filter = ("emoji",)


@admin.register(DirectMessage)
class DirectMessageAdmin(admin.ModelAdmin):
    list_display = ("author", "conversation", "created_at", "snippet")

    @admin.display(description="Treść")
    def snippet(self, obj: DirectMessage) -> str:
        return (obj.content or "")[:50] or "(załącznik)"


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "channel_type", "server", "created_at")
    list_filter = ("channel_type", "server")


@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    list_display = ("emoji", "message", "user", "created_at")
    list_filter = ("emoji", "message__channel__server")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("author", "channel", "created_at", "has_attachment")
    list_filter = ("channel__server", "created_at")
    readonly_fields = ("created_at",)

    @admin.display(description="Załącznik", boolean=True)
    def has_attachment(self, obj: Message) -> bool:
        return bool(obj.attachment)
