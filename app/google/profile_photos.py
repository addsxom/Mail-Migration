import hashlib
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from googleapiclient.discovery import build

from app.core.config import DATA_DIR
from .oauth import load_credentials

PHOTO_CACHE_DIR = DATA_DIR / "profile_photos"
PHOTO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CONTACT_PHOTOS = {}


def _cache_path(sender_email):
    key = hashlib.sha256(sender_email.strip().casefold().encode("utf-8")).hexdigest()
    return PHOTO_CACHE_DIR / f"{key}.jpg"


def _download(url, destination, token=None):
    headers = {"User-Agent": "Mail-Migration/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=8) as response:
        data = response.read()
    if not data:
        return False
    destination.write_bytes(data)
    return True


def _load_google_contacts(account_email):
    if account_email in _CONTACT_PHOTOS:
        return _CONTACT_PHOTOS[account_email]
    credentials = load_credentials(account_email)
    if not credentials:
        _CONTACT_PHOTOS[account_email] = {}
        return {}
    service = build("people", "v1", credentials=credentials, cache_discovery=False)
    result = {}
    token = None
    while True:
        response = service.people().connections().list(
            resourceName="people/me",
            pageSize=1000,
            pageToken=token,
            personFields="emailAddresses,photos",
        ).execute()
        for person in response.get("connections", []):
            photos = [item.get("url") for item in person.get("photos", []) if item.get("url")]
            if not photos:
                continue
            for item in person.get("emailAddresses", []):
                email = item.get("value", "").strip().casefold()
                if email:
                    result[email] = (photos[0], credentials.token)
        token = response.get("nextPageToken")
        if not token:
            break
    try:
        token = None
        while True:
            response = service.otherContacts().list(
                pageSize=1000,
                pageToken=token,
                readMask="emailAddresses,photos",
            ).execute()
            for person in response.get("otherContacts", []):
                photos = [item.get("url") for item in person.get("photos", []) if item.get("url")]
                if not photos:
                    continue
                for item in person.get("emailAddresses", []):
                    email = item.get("value", "").strip().casefold()
                    if email and email not in result:
                        result[email] = (photos[0], credentials.token)
            token = response.get("nextPageToken")
            if not token:
                break
    except Exception:
        pass
    _CONTACT_PHOTOS[account_email] = result
    return result


def _gravatar_photo(sender_email):
    digest = hashlib.md5(sender_email.strip().casefold().encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?s=128&d=404"


def get_profile_photo(sender_email, account_email):
    sender_email = (sender_email or "").strip().casefold()
    account_email = (account_email or "").strip().casefold()
    if not sender_email or not account_email:
        return None

    cached = _cache_path(sender_email)
    if cached.exists() and cached.stat().st_size:
        return str(cached)

    try:
        match = _load_google_contacts(account_email).get(sender_email)
        if match and _download(match[0], cached, match[1]):
            return str(cached)
    except Exception:
        pass

    try:
        if _download(_gravatar_photo(sender_email), cached):
            return str(cached)
    except (HTTPError, URLError, TimeoutError, OSError):
        pass

    return None
