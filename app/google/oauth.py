import logging
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from app.core.config import CREDENTIALS_FILE, TOKENS_DIR, GMAIL_SCOPES

log = logging.getLogger(__name__)

def token_path_for_email(email: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in email.lower())
    return TOKENS_DIR / f"{safe}.json"

def authorize():
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"credentials.json introuvable : {CREDENTIALS_FILE}"
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        scopes=GMAIL_SCOPES,
    )
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile["emailAddress"]

    path = token_path_for_email(email)
    path.write_text(creds.to_json(), encoding="utf-8")
    return email, path.name

def load_credentials(email: str):
    path = token_path_for_email(email)
    if not path.exists():
        return None

    creds = Credentials.from_authorized_user_file(str(path), GMAIL_SCOPES)
    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    return None

def revoke_token(email: str):
    path = token_path_for_email(email)
    if path.exists():
        path.unlink()
