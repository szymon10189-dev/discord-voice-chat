from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path(
        "api/channels/<int:channel_id>/messages/<int:message_id>/delete/",
        views.ChatMessageDeleteView.as_view(),
        name="chat_message_delete",
    ),
    path(
        "api/channels/<int:channel_id>/messages/upload/",
        views.ChatMessageUploadView.as_view(),
        name="chat_message_upload",
    ),
    path(
        "api/servers/<int:server_id>/users/<int:user_id>/block/",
        views.ServerUserBlockView.as_view(),
        name="server_user_block",
    ),
    path(
        "api/servers/<int:server_id>/users/<int:user_id>/unblock/",
        views.ServerUserUnblockView.as_view(),
        name="server_user_unblock",
    ),
    path("login/", views.AppLoginView.as_view(), name="login"),
    path("logout/", views.AppLogoutView.as_view(), name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("profile/", views.ProfileEditView.as_view(), name="profile_edit"),
    path("dm/", views.DirectMessageInboxView.as_view(), name="dm_inbox"),
    path("dm/<int:user_id>/", views.DirectMessageThreadView.as_view(), name="dm_thread"),
    path(
        "dashboard/<int:server_id>/channel/<int:channel_id>/",
        views.DashboardView.as_view(),
        name="dashboard_channel",
    ),
    path(
        "dashboard/<int:server_id>/",
        views.DashboardView.as_view(),
        name="dashboard",
    ),
    path("", views.HomeView.as_view(), name="home"),
]
