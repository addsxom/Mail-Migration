import hashlib
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from googleapiclient.discovery import build

from app.core.config import DATA_DIR
from .oauth import load_credentials

PHOTO_CACHE_DIR = DATA_DIR / "profile_photos"
PHOTO_CACHE_DIR.mkdir(parents=True, exist_ok=True)


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


def _people_photo(sender_email, account_email):
    credentials = load_credentials(account_email)
    if not credentials:
        return None
    service = build("people", "v1", credentials=credentials, cache_discovery=False)
    response = service.people().searchContacts(
        query=sender_email,
        readMask="emailAddresses,names,photos",
        pageSize=10,
    ).execute()
    target = sender_email.casefold()
    for result in response.get("results", []):
        person = result.get("person", {})
        emails = {
            item.get("value", "").casefold()
            for item in person.get("emailAddresses", [])
            if item.get("value")
        }
        if target not in emails:
            continue
        for photo in person.get("photos", []):
            url = photo.get("url")
            if url:
                return url, credentials.token
    return None


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
        result = _people_photo(sender_email, account_email)
        if result:
            url, token = result
            if _download(url, cached, token):
                return str(cached)
    except Exception:
        pass

    try:
        if _download(_gravatar_photo(sender_email), cached):
            return str(cached)
    except (HTTPError, URLError, TimeoutError, OSError):
        pass

    return None
