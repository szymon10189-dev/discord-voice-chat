"""Pomocnicze funkcje dla wiadomości prywatnych (DM)."""

from django.contrib.auth import get_user_model

from .models import DirectConversation

User = get_user_model()


def get_or_create_direct_conversation(user1: User, user2: User) -> DirectConversation:
    """Zwraca istniejącą lub nową rozmowę między dwoma różnymi użytkownikami."""
    if user1.pk == user2.pk:
        raise ValueError("Nie można utworzyć rozmowy z samym sobą.")
    a, b = (user1, user2) if user1.pk < user2.pk else (user2, user1)
    conv, _ = DirectConversation.objects.get_or_create(user_a=a, user_b=b)
    return conv


def user_participates_in_conversation(user, conversation: DirectConversation) -> bool:
    return user.pk in (conversation.user_a_id, conversation.user_b_id)
