import json
import logging
from pathlib import Path
from urllib import parse, request

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from app.core.config import CREDENTIALS_FILE, TOKENS_DIR, GMAIL_SCOPES

log = logging.getLogger(__name__)


def token_path_for_email(email: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in email.lower())
    return TOKENS_DIR / f"{safe}.json"


def authorize():
    """Run Google OAuth and store a token dedicated to the authorized account."""
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(f"credentials.json introuvable : {CREDENTIALS_FILE}")

    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        scopes=GMAIL_SCOPES,
    )
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )

    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile["emailAddress"].lower()

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


def credential_state(email: str) -> str:
    """Return a UI-safe token state without exposing token contents."""
    path = token_path_for_email(email)
    if not path.exists():
        return "Autorisation requise"

    try:
        creds = Credentials.from_authorized_user_file(str(path), GMAIL_SCOPES)
    except (ValueError, OSError, json.JSONDecodeError):
        return "Autorisation requise"

    if creds and creds.valid:
        return "Connecté"
    if creds and creds.expired and creds.refresh_token:
        return "À actualiser"
    return "Autorisation requise"


def revoke_token(email: str):
    """Revoke the Google OAuth token server-side, then remove the local token."""
    path = token_path_for_email(email)
    if not path.exists():
        return

    try:
        creds = Credentials.from_authorized_user_file(str(path), GMAIL_SCOPES)
        token = creds.refresh_token or creds.token
        if token:
            data = parse.urlencode({"token": token}).encode("utf-8")
            req = request.Request(
                "https://oauth2.googleapis.com/revoke",
                data=data,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with request.urlopen(req, timeout=10):
                pass
    except Exception as exc:
        log.warning("Google token revocation failed; removing local token anyway: %s", exc.__class__.__name__)
    finally:
        if path.exists():
            path.unlink()
