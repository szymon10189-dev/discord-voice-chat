from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/presence/", consumers.SitePresenceConsumer.as_asgi()),
    path("ws/chat/<int:channel_id>/", consumers.ChatConsumer.as_asgi()),
    path("ws/voice/<int:channel_id>/", consumers.VoiceConsumer.as_asgi()),
]
