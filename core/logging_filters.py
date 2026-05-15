import asyncio
import logging


class SuppressCancelledDisconnectFilter(logging.Filter):
    """
    Nie loguj asyncio.CancelledError przy zerwaniu połączenia HTTP — to normalne pod ASGI
    (np. użytkownik odświeżył stronę w trakcie żądania), a asgiref zapisuje to jako ERROR.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and record.exc_info[0] is not None:
            if record.exc_info[0] is asyncio.CancelledError:
                return False
        msg = record.getMessage()
        if "CancelledError" in msg and "shielded" in msg.lower():
            return False
        return True
