import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from googleapiclient.discovery import build

from app.core.config import DATA_DIR
from .oauth import load_credentials

PHOTO_CACHE_DIR = DATA_DIR / "profile_photos"
PHOTO_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(email):
    key = hashlib.sha256(email.strip().casefold().encode("utf-8")).hexdigest()
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


def _people_photo(email, credentials):
    service = build("people", "v1", credentials=credentials, cache_discovery=False)
    response = service.people().searchContacts(
        query=email,
        readMask="emailAddresses,names,photos",
        pageSize=10,
    ).execute()
    target = email.casefold()
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
                return url
    return None


def _gravatar_photo(email):
    digest = hashlib.md5(email.strip().casefold().encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?s=128&d=404"


def get_profile_photo(email):
    email = (email or "").strip().casefold()
    if not email:
        return None
    cached = _cache_path(email)
    if cached.exists() and cached.stat().st_size:
        return str(cached)

    credentials = load_credentials(email)
    if credentials:
        try:
            photo_url = _people_photo(email, credentials)
            if photo_url and _download(photo_url, cached, credentials.token):
                return str(cached)
        except Exception:
            pass

    try:
        if _download(_gravatar_photo(email), cached):
            return str(cached)
    except (HTTPError, URLError, TimeoutError, OSError):
        pass

    return None
