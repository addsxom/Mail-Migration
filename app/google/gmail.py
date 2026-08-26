import time
from typing import Callable, Iterator

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import MAX_MESSAGES_PER_PAGE
from .oauth import load_credentials


MAX_RETRIES = 4
RETRY_BASE_DELAY = 1.0


def get_gmail_service(email: str):
    creds = load_credentials(email)
    if not creds:
        raise RuntimeError(f"Autorisation Gmail indisponible pour {email}.")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, HttpError):
        status = getattr(exc.resp, "status", None)
        return status in {408, 429, 500, 502, 503, 504}
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


def _execute_with_retry(request_factory: Callable[[], object]):
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return request_factory().execute()
        except Exception as exc:
            last_error = exc
            if attempt >= MAX_RETRIES or not _is_retryable(exc):
                raise
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    raise last_error  # pragma: no cover


def get_profile(email: str):
    service = get_gmail_service(email)
    return _execute_with_retry(
        lambda: service.users().getProfile(userId="me")
    )


def get_message_count(email: str, query: str = "") -> int:
    """Return Gmail's estimated number of messages matching the query."""
    service = get_gmail_service(email)
    response = _execute_with_retry(
        lambda: service.users().messages().list(
            userId="me",
            q=query,
            maxResults=1,
        )
    )
    return int(response.get("resultSizeEstimate", 0) or 0)


def iter_message_metadata(
    email: str,
    query: str = "",
    cancel_check=None,
) -> Iterator[dict]:
    service = get_gmail_service(email)
    token = None

    while True:
        if cancel_check and cancel_check():
            return

        response = _execute_with_retry(
            lambda: service.users().messages().list(
                userId="me",
                q=query,
                pageToken=token,
                maxResults=MAX_MESSAGES_PER_PAGE,
            )
        )

        for item in response.get("messages", []):
            if cancel_check and cancel_check():
                return

            message_id = item.get("id")
            if not message_id:
                continue

            msg = _execute_with_retry(
                lambda message_id=message_id: service.users().messages().get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                )
            )
            yield msg

        token = response.get("nextPageToken")
        if not token:
            break
