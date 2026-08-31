from datetime import datetime, timezone
from pathlib import Path
import json
import re
import shutil
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sqlalchemy import select

from app.database.models import GoogleAccount, AccountService, ScanHistory, ScanServiceSnapshot, ScanTrace
from app.database.repositories import get_or_create_service
from app.google.gmail import get_message_count, iter_message_metadata
from app.google.profile_photos import get_profile_photo
from app.services.builtin_catalog import CATALOG
from app.scanner.intelligent_services import resolve_service
from .catalog_index import CatalogIndex
from .detector import detect_message


class ScanCancelled(Exception):
    pass


UNKNOWN_MIN_MESSAGES = 2
PERSIST_EVERY_MESSAGES = 50

# The scanner deliberately does not call the Qt/UI layer for every message.
# The UI receives throttled progress updates from ScanWorker instead.

SERVICE_WEBSITES = {
    "streamlabs": "streamlabs.com", "medal": "medal.tv", "supercell": "supercell.com",
    "supercell-store": "store.supercell.com", "brawl-stars": "brawlstars.com", "guns-lol": "guns.lol",
    "sony": "sony.com", "hide-me": "hide.me", "intelligence-x": "intelx.io", "sellhub": "sellhub.com",
    "bitwarden": "bitwarden.com", "shein": "shein.com", "lego": "lego.com", "just-eat": "just-eat.ch",
    "instant-gaming": "instant-gaming.com", "ebookers": "ebookers.com", "hellcase": "hellcase.com",
    "tinder": "tinder.com", "mongodb": "mongodb.com", "eneba": "eneba.com", "chess-com": "chess.com", "bolt": "bolt.eu",
}


def _service_key(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name or "service").strip().lower()).strip("-") or "service"


def _service_initials(name):
    words = [word for word in re.split(r"\s+", str(name or "Service").strip()) if word]
    if not words:
        return "?"
    if len(words) == 1:
        value = re.sub(r"[^A-Za-z0-9]", "", words[0])
        return (value[:2] or "?").upper()
    return (words[0][0] + words[1][0]).upper()


def _service_website(service_name, sender_email):
    key = _service_key(service_name)
    if key in SERVICE_WEBSITES:
        return SERVICE_WEBSITES[key]
    domain = (sender_email or "").rsplit("@", 1)[-1].strip().lower()
    return domain if domain and "." in domain else None


def _download_logo(url, destination):
    request = Request(url, headers={"User-Agent": "Mail-Migration/1.0"})
    with urlopen(request, timeout=5) as response:
        data = response.read()
        content_type = (response.headers.get("Content-Type") or "").lower()
    if not data or len(data) < 32:
        return False
    if "svg" in content_type or data.lstrip().startswith(b"<svg") or b"<svg" in data[:500].lower():
        destination = destination.with_suffix(".svg")
    elif "png" in content_type or data.startswith(b"\x89PNG"):
        destination = destination.with_suffix(".png")
    elif "webp" in content_type or (data.startswith(b"RIFF") and b"WEBP" in data[:16]):
        destination = destination.with_suffix(".webp")
    else:
        destination = destination.with_suffix(".jpg")
    destination.write_bytes(data)
    return True


def _download_service_logo(service_name, sender_email, assets, key):
    website = _service_website(service_name, sender_email)
    if not website:
        return False
    candidates = [
        f"https://{website}/favicon.ico",
        f"https://www.{website}/favicon.ico" if not website.startswith("www.") else None,
        f"https://www.google.com/s2/favicons?sz=128&domain={quote(website)}",
    ]
    for url in candidates:
        if not url:
            continue
        try:
            if _download_logo(url, assets / key):
                return True
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            continue
    return False


def _is_placeholder_avatar(path):
    if path.suffix.lower() != ".svg":
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return '<circle cx="32" cy="32" r="30" fill="#303846"' in content and '<text x="32" y="35"' in content


def _remove_placeholder_avatar(assets, key):
    path = assets / f"{key}.svg"
    if _is_placeholder_avatar(path):
        try:
            path.unlink()
        except OSError:
            pass


def _write_service_avatar(service_name, sender_email, account_email):
    assets = Path(__file__).resolve().parents[2] / "assets" / "service_logos"
    assets.mkdir(parents=True, exist_ok=True)
    key = _service_key(service_name)
    existing = [assets / f"{key}{suffix}" for suffix in (".png", ".jpg", ".jpeg", ".svg", ".webp")]
    if any(path.exists() and path.stat().st_size > 32 and not _is_placeholder_avatar(path) for path in existing):
        return
    _remove_placeholder_avatar(assets, key)
    if sender_email:
        try:
            photo = get_profile_photo(sender_email, account_email)
            if photo and Path(photo).exists() and Path(photo).stat().st_size > 32:
                shutil.copyfile(photo, assets / f"{key}.jpg")
                return
        except (OSError, ValueError):
            pass
    if _download_service_logo(service_name, sender_email, assets, key):
        return
    initials = _service_initials(service_name)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><circle cx="32" cy="32" r="30" fill="#303846"/><text x="32" y="35" text-anchor="middle" dominant-baseline="middle" fill="#E7EAF0" font-family="Arial,sans-serif" font-size="18" font-weight="700">{initials}</text></svg>'''
    (assets / f"{key}.svg").write_text(svg, encoding="utf-8")


def _persist_detection(session, account, data):
    service = get_or_create_service(session, data["definition"])
    sender_email = data.get("sender_email")
    if sender_email:
        try:
            senders = json.loads(service.senders_json or "[]")
        except (TypeError, ValueError):
            senders = []
        if sender_email not in senders:
            senders.append(sender_email)
            service.senders_json = json.dumps(senders, ensure_ascii=False)
        try:
            _write_service_avatar(service.name, sender_email, account.email)
        except Exception:
            pass
    link = session.scalar(select(AccountService).where(AccountService.account_id == account.id, AccountService.service_id == service.id))
    now = datetime.now(timezone.utc)
    if not link:
        link = AccountService(account_id=account.id, service_id=service.id, confidence_score=data["score"], trace_count=0, first_detected_at=now, last_detected_at=now, status="À vérifier")
        session.add(link)
        session.flush()
    else:
        link.confidence_score = max(link.confidence_score, data["score"])
        link.last_detected_at = now
    existing_ids = {row.message_id for row in session.scalars(select(ScanTrace).where(ScanTrace.account_service_id == link.id))}
    signal = sorted(data["signals"])[0] if data["signals"] else "unknown"
    signal_value = ", ".join(sorted(data["signals"]))
    for message_id in data["message_ids"]:
        if message_id and message_id not in existing_ids:
            session.add(ScanTrace(account_service_id=link.id, message_id=message_id, signal_type=signal, signal_value=signal_value))
            existing_ids.add(message_id)
    link.trace_count = len(existing_ids)
    return link


def _persist_partial(session, account, detections, detection_callback=None):
    callbacks = []
    for data in detections.values():
        link = _persist_detection(session, account, data)
        if detection_callback:
            callbacks.append((data, link))
    session.commit()
    if detection_callback:
        for data, link in callbacks:
            detection_callback(_callback_data(account, data, link))


def _new_detection_bucket(detection):
    return {"definition": detection.service, "score": detection.score, "signals": set(detection.signals), "count": 0, "message_ids": [], "reliability": detection.reliability, "sender_email": detection.sender_email}


def _add_detection(bucket, detection, message_id):
    bucket["score"] = max(bucket["score"], detection.score)
    bucket["signals"].update(detection.signals)
    bucket["count"] += 1
    bucket["reliability"] = detection.reliability
    if detection.sender_email:
        bucket["sender_email"] = detection.sender_email
    if message_id and message_id not in bucket["message_ids"]:
        bucket["message_ids"].append(message_id)


def _callback_data(account, item, link=None):
    return {"account_id": account.id, "account_service_id": link.id if link else None, "account_email": account.email, "name": item["definition"]["name"], "service_id": item["definition"].get("name"), "category": item["definition"].get("category", "Autre"), "subcategory": item["definition"].get("subcategory"), "score": item["score"], "count": item["count"], "status": link.status if link else "À vérifier", "priority": (link.priority or "Normale") if link else "Normale", "destination_email": link.destination_email if link else None, "notes": link.notes if link else None, "first_detected_at": link.first_detected_at if link else None, "last_detected_at": link.last_detected_at if link else None, "signals": sorted(item["signals"]), "reliability": item.get("reliability", {}), "sender_email": item.get("sender_email")}


def _save_scan_snapshot(session, history, account):
    services = session.scalars(select(AccountService).where(AccountService.account_id == account.id).order_by(AccountService.confidence_score.desc())).all()
    for link in services:
        service = link.service
        session.add(ScanServiceSnapshot(scan_history_id=history.id, service_name=service.name if service else "Service inconnu", category=service.category if service else "Autre", confidence_score=link.confidence_score or 0, trace_count=link.trace_count or 0, status=link.status or "À vérifier", priority=link.priority or "Normale", destination_email=link.destination_email, notes=link.notes))


def scan_account(session, account_id, progress=None, cancel_check=None, query="", detection_callback=None):
    account = session.get(GoogleAccount, account_id)
    if not account:
        raise ValueError("Compte introuvable.")
    if not account.active:
        raise ValueError("Le compte est désactivé.")
    history = ScanHistory(account_id=account.id, status="running")
    session.add(history)
    session.commit()
    detections = {}
    unknown_candidates = {}
    messages_scanned = 0
    estimated_total = 0
    last_persist = 0
    catalog_index = CatalogIndex(CATALOG)
    # Only these counters are sent to the worker. No Qt objects are touched here.
    last_progress_emit = 0
    try:
        estimated_total = get_message_count(account.email, query=query)
        if progress:
            progress(0, estimated_total, 0)
        for message in iter_message_metadata(account.email, query=query, cancel_check=cancel_check):
            if cancel_check and cancel_check():
                _persist_partial(session, account, detections, detection_callback)
                raise ScanCancelled()
            messages_scanned += 1
            message_id = message.get("id", "")
            results = detect_message(message, CATALOG, catalog_index=catalog_index)
            for detection in results:
                key = detection.service["name"]
                if detection.service.get("unknown"):
                    item = unknown_candidates.setdefault(key, _new_detection_bucket(detection))
                    _add_detection(item, detection, message_id)
                    if item["count"] < UNKNOWN_MIN_MESSAGES:
                        continue
                    detections[key] = item
                else:
                    item = detections.setdefault(key, _new_detection_bucket(detection))
                    _add_detection(item, detection, message_id)
                # Detection callbacks are intentionally batched by the UI worker.
                # This callback remains available for compatibility with existing callers.
                if detection_callback:
                    detection_callback(_callback_data(account, item))
            if messages_scanned - last_persist >= PERSIST_EVERY_MESSAGES:
                _persist_partial(session, account, detections, detection_callback)
                last_persist = messages_scanned
            if progress and (messages_scanned - last_progress_emit >= 25 or messages_scanned == estimated_total):
                progress(messages_scanned, estimated_total, len(detections))
                last_progress_emit = messages_scanned
        _persist_partial(session, account, detections, detection_callback)
        finished_at = datetime.now(timezone.utc)
        account.last_scan_at = finished_at
        history.finished_at = finished_at
        history.status = "completed"
        history.messages_scanned = messages_scanned
        history.services_detected = len(detections)
        _save_scan_snapshot(session, history, account)
        session.commit()
        if progress:
            progress(messages_scanned, estimated_total, len(detections))
        return messages_scanned, len(detections)
    except ScanCancelled:
        session.rollback()
        history = session.get(ScanHistory, history.id)
        if history:
            history.finished_at = datetime.now(timezone.utc)
            history.status = "cancelled"
            history.messages_scanned = messages_scanned
            history.services_detected = len(detections)
            session.commit()
        raise
    except Exception as exc:
        session.rollback()
        history = session.get(ScanHistory, history.id)
        if history:
            history.finished_at = datetime.now(timezone.utc)
            history.status = "error"
            history.messages_scanned = messages_scanned
            history.services_detected = len(detections)
            history.error = str(exc)
            session.commit()
        raise
