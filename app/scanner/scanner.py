from datetime import datetime, timezone

from sqlalchemy import select

from app.database.models import GoogleAccount, AccountService, ScanHistory, ScanTrace
from app.database.repositories import get_or_create_service
from app.google.gmail import get_message_count, iter_message_metadata
from app.services.builtin_catalog import CATALOG
from .catalog_index import CatalogIndex
from .detector import detect_message


class ScanCancelled(Exception):
    pass


UNKNOWN_MIN_MESSAGES = 2
PERSIST_EVERY_MESSAGES = 50


def _persist_detection(session, account, data):
    service = get_or_create_service(session, data["definition"])
    link = session.scalar(
        select(AccountService).where(
            AccountService.account_id == account.id,
            AccountService.service_id == service.id,
        )
    )
    now = datetime.now(timezone.utc)

    if not link:
        link = AccountService(
            account_id=account.id,
            service_id=service.id,
            confidence_score=data["score"],
            trace_count=0,
            first_detected_at=now,
            last_detected_at=now,
            status="À vérifier",
        )
        session.add(link)
        session.flush()
    else:
        link.confidence_score = max(link.confidence_score, data["score"])
        link.last_detected_at = now

    existing_ids = {
        row.message_id
        for row in session.scalars(
            select(ScanTrace).where(
                ScanTrace.account_service_id == link.id
            )
        )
    }

    signal = sorted(data["signals"])[0] if data["signals"] else "unknown"
    signal_value = ", ".join(sorted(data["signals"]))

    for message_id in data["message_ids"]:
        if message_id and message_id not in existing_ids:
            session.add(
                ScanTrace(
                    account_service_id=link.id,
                    message_id=message_id,
                    signal_type=signal,
                    signal_value=signal_value,
                )
            )
            existing_ids.add(message_id)

    link.trace_count = len(existing_ids)
    return link


def _persist_partial(session, account, detections, detection_callback=None):
    """Persist accumulated detections in one transaction and emit callbacks once."""
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
    return {
        "definition": detection.service,
        "score": detection.score,
        "signals": set(detection.signals),
        "count": 0,
        "message_ids": [],
        "reliability": detection.reliability,
    }


def _add_detection(bucket, detection, message_id):
    bucket["score"] = max(bucket["score"], detection.score)
    bucket["signals"].update(detection.signals)
    bucket["count"] += 1
    bucket["reliability"] = detection.reliability
    if message_id and message_id not in bucket["message_ids"]:
        bucket["message_ids"].append(message_id)


def _callback_data(account, item, link):
    return {
        "account_id": account.id,
        "account_service_id": link.id,
        "account_email": account.email,
        "name": item["definition"]["name"],
        "service_id": item["definition"].get("name"),
        "category": item["definition"].get("category", "Autre"),
        "subcategory": item["definition"].get("subcategory"),
        "score": item["score"],
        "count": item["count"],
        "status": link.status or "À vérifier",
        "priority": link.priority or "Normale",
        "destination_email": link.destination_email,
        "notes": link.notes,
        "first_detected_at": link.first_detected_at,
        "last_detected_at": link.last_detected_at,
        "signals": sorted(item["signals"]),
        "reliability": item.get("reliability", {}),
    }


def scan_account(
    session,
    account_id,
    progress=None,
    cancel_check=None,
    query="",
    detection_callback=None,
):
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

    try:
        estimated_total = get_message_count(account.email, query=query)
        if progress:
            progress(0, estimated_total, 0)

        for message in iter_message_metadata(
            account.email,
            query=query,
            cancel_check=cancel_check,
        ):
            if cancel_check and cancel_check():
                _persist_partial(
                    session,
                    account,
                    detections,
                    detection_callback,
                )
                raise ScanCancelled()

            messages_scanned += 1
            message_id = message.get("id", "")
            results = detect_message(
                message,
                CATALOG,
                catalog_index=catalog_index,
            )

            for detection in results:
                key = detection.service["name"]

                if detection.service.get("unknown"):
                    item = unknown_candidates.setdefault(
                        key,
                        _new_detection_bucket(detection),
                    )
                    _add_detection(item, detection, message_id)

                    if item["count"] < UNKNOWN_MIN_MESSAGES:
                        continue
                    detections[key] = item
                else:
                    item = detections.setdefault(
                        key,
                        _new_detection_bucket(detection),
                    )
                    _add_detection(item, detection, message_id)

            if messages_scanned - last_persist >= PERSIST_EVERY_MESSAGES:
                _persist_partial(
                    session,
                    account,
                    detections,
                    detection_callback,
                )
                last_persist = messages_scanned

            if progress:
                progress(
                    messages_scanned,
                    estimated_total,
                    len(detections),
                )

        _persist_partial(
            session,
            account,
            detections,
            detection_callback,
        )

        account.last_scan_at = datetime.now(timezone.utc)
        history.finished_at = datetime.now(timezone.utc)
        history.status = "completed"
        history.messages_scanned = messages_scanned
        history.services_detected = len(detections)
        session.commit()

        if progress:
            progress(
                messages_scanned,
                estimated_total,
                len(detections),
            )
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
