from googleapiclient.discovery import build
from app.core.config import MAX_MESSAGES_PER_PAGE
from .oauth import load_credentials

def get_gmail_service(email: str):
    creds = load_credentials(email)
    if not creds:
        raise RuntimeError(f"Autorisation Gmail indisponible pour {email}.")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def get_profile(email: str):
    service = get_gmail_service(email)
    return service.users().getProfile(userId="me").execute()

def iter_message_metadata(email: str, query="", cancel_check=None):
    service = get_gmail_service(email)
    token = None

    while True:
        if cancel_check and cancel_check():
            return

        response = service.users().messages().list(
            userId="me",
            q=query,
            pageToken=token,
            maxResults=MAX_MESSAGES_PER_PAGE,
        ).execute()

        for item in response.get("messages", []):
            if cancel_check and cancel_check():
                return

            msg = service.users().messages().get(
                userId="me",
                id=item["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()

            yield msg

        token = response.get("nextPageToken")
        if not token:
            break
