"""Walidacja i tworzenie zgłoszeń użytkowników."""

from django.core.exceptions import ValidationError

from .models import Message, UserReport

REPORT_REASON_MIN_LEN = 10
REPORT_REASON_MAX_LEN = 2000


def validate_report_reason(reason: str) -> str:
    value = (reason or "").strip()
    if len(value) < REPORT_REASON_MIN_LEN:
        raise ValidationError(
            f"Opisz problem (minimum {REPORT_REASON_MIN_LEN} znaków).",
        )
    if len(value) > REPORT_REASON_MAX_LEN:
        raise ValidationError(
            f"Powód zgłoszenia jest za długi (maks. {REPORT_REASON_MAX_LEN} znaków).",
        )
    return value


def create_user_report(
    *,
    reporter,
    reported_user,
    reason: str,
    server=None,
    message=None,
) -> UserReport:
    if reporter.pk == reported_user.pk:
        raise ValidationError("Nie możesz zgłosić samego siebie.")

    reason = validate_report_reason(reason)

    if message is not None and message.author_id != reported_user.pk:
        raise ValidationError("Wiadomość nie należy do zgłaszanego użytkownika.")

    return UserReport.objects.create(
        reporter=reporter,
        reported_user=reported_user,
        server=server,
        message=message,
        reason=reason,
    )
