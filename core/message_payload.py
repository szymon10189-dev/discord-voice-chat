"""Serializacja wiadomości czatu (WebSocket + HTTP upload)."""

import mimetypes
from pathlib import Path

from .models import Message

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}
AUDIO_EXT = {
    ".webm",
    ".wav",
    ".ogg",
    ".opus",
    ".mp3",
    ".m4a",
    ".aac",
    ".mpeg",
    ".mpga",
    ".flac",
}


def classify_attachment_kind(filename: str) -> str:
    """Zwraca: none | image | audio | file — na podstawie nazwy pliku i MIME."""
    if not filename:
        return "none"
    mime, _ = mimetypes.guess_type(filename)
    ext = Path(filename).suffix.lower()
    if mime:
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("audio/"):
            return "audio"
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    return "file"


def build_message_payload(msg: Message) -> dict:
    msg = Message.objects.select_related("author").get(pk=msg.pk)
    author = msg.author
    avatar_url = ""
    if getattr(author, "avatar", None) and author.avatar:
        avatar_url = author.avatar.url

    att_url = ""
    att_kind = "none"
    att_mime = ""
    if msg.attachment:
        att_url = msg.attachment.url
        att_mime, _ = mimetypes.guess_type(msg.attachment.name)
        att_mime = att_mime or ""
        att_kind = classify_attachment_kind(msg.attachment.name)

    return {
        "id": msg.id,
        "author_id": author.id,
        "author_username": author.username,
        "author_avatar_url": avatar_url,
        "content": msg.content or "",
        "created_at": msg.created_at.isoformat(),
        "attachment_url": att_url,
        "attachment_kind": att_kind,
        "attachment_mime": att_mime,
    }
