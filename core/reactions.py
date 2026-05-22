"""Reakcje emoji na wiadomościach kanału i w DM."""

from __future__ import annotations

from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db.models import Count

from .models import DirectMessage, DirectMessageReaction, Message, MessageReaction

# Szybki wybór w UI + walidacja (dowolne emoji z tej listy).
QUICK_REACTION_EMOJIS = (
    "👍",
    "❤️",
    "😂",
    "😮",
    "😢",
    "🔥",
    "👏",
    "🎉",
    "✅",
    "❌",
    "⭐",
    "💯",
)

_ALLOWED = frozenset(QUICK_REACTION_EMOJIS)


def validate_reaction_emoji(emoji: str) -> str:
    value = (emoji or "").strip()
    if value not in _ALLOWED:
        raise ValidationError("Niedozwolone emoji reakcji.")
    return value


def reactions_summary_for_messages(
    message_ids: list[int],
    viewer_id: int,
) -> dict[int, list[dict]]:
    """message_id -> [{emoji, count, reacted_by_me}, ...] posortowane malejąco po liczbie."""
    if not message_ids:
        return {}

    rows = (
        MessageReaction.objects.filter(message_id__in=message_ids)
        .values("message_id", "emoji")
        .annotate(count=Count("id"))
        .order_by("message_id", "-count", "emoji")
    )

    user_rows = MessageReaction.objects.filter(
        message_id__in=message_ids,
        user_id=viewer_id,
    ).values_list("message_id", "emoji")

    mine: dict[int, set[str]] = defaultdict(set)
    for mid, emoji in user_rows:
        mine[mid].add(emoji)

    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        mid = row["message_id"]
        emoji = row["emoji"]
        grouped[mid].append(
            {
                "emoji": emoji,
                "count": row["count"],
                "reacted_by_me": emoji in mine.get(mid, set()),
            }
        )

    return {mid: grouped.get(mid, []) for mid in message_ids}


def reactions_summary_for_message(message_id: int, viewer_id: int) -> list[dict]:
    return reactions_summary_for_messages([message_id], viewer_id).get(message_id, [])


def attach_reactions_to_messages(messages: list[Message], viewer) -> None:
    ids = [m.id for m in messages if m.id]
    summary = reactions_summary_for_messages(ids, viewer.pk)
    for msg in messages:
        msg.reaction_rows = summary.get(msg.id, [])


def toggle_message_reaction(message: Message, user, emoji: str) -> list[dict]:
    emoji = validate_reaction_emoji(emoji)
    existing = MessageReaction.objects.filter(
        message=message,
        user=user,
        emoji=emoji,
    ).first()
    if existing:
        existing.delete()
    else:
        MessageReaction.objects.create(message=message, user=user, emoji=emoji)
    return reactions_summary_for_message(message.pk, user.pk)


def dm_reactions_summary_for_messages(
    message_ids: list[int],
    viewer_id: int,
) -> dict[int, list[dict]]:
    if not message_ids:
        return {}

    rows = (
        DirectMessageReaction.objects.filter(message_id__in=message_ids)
        .values("message_id", "emoji")
        .annotate(count=Count("id"))
        .order_by("message_id", "-count", "emoji")
    )

    user_rows = DirectMessageReaction.objects.filter(
        message_id__in=message_ids,
        user_id=viewer_id,
    ).values_list("message_id", "emoji")

    mine: dict[int, set[str]] = defaultdict(set)
    for mid, emoji in user_rows:
        mine[mid].add(emoji)

    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        mid = row["message_id"]
        emoji = row["emoji"]
        grouped[mid].append(
            {
                "emoji": emoji,
                "count": row["count"],
                "reacted_by_me": emoji in mine.get(mid, set()),
            }
        )

    return {mid: grouped.get(mid, []) for mid in message_ids}


def dm_reactions_summary_for_message(message_id: int, viewer_id: int) -> list[dict]:
    return dm_reactions_summary_for_messages([message_id], viewer_id).get(
        message_id,
        [],
    )


def attach_reactions_to_direct_messages(messages: list[DirectMessage], viewer) -> None:
    ids = [m.id for m in messages if m.id]
    summary = dm_reactions_summary_for_messages(ids, viewer.pk)
    for msg in messages:
        msg.reaction_rows = summary.get(msg.id, [])


def toggle_direct_message_reaction(
    message: DirectMessage,
    user,
    emoji: str,
) -> list[dict]:
    emoji = validate_reaction_emoji(emoji)
    existing = DirectMessageReaction.objects.filter(
        message=message,
        user=user,
        emoji=emoji,
    ).first()
    if existing:
        existing.delete()
    else:
        DirectMessageReaction.objects.create(message=message, user=user, emoji=emoji)
    return dm_reactions_summary_for_message(message.pk, user.pk)
