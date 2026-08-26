from datetime import datetime, timezone

from sqlalchemy import select

from app.database.models import GoogleAccount, AccountService, ScanHistory, ScanTrace
from app.database.repositories import get_or_create_service
from app.google.gmail import get_message_count, iter_message_metadata
from app.services.builtin_catalog import CATALOG
from .detector import detect_message


class ScanCancelled(Exception):
    pass


# TEMPORAIRE POUR LES TESTS : chaque compte s'arrête après 30 services distincts.
# À retirer une fois les tests multi-comptes validés.
TEST_SERVICE_LIMIT = 30


def _persist_partial(session, account, detections):
    for data in detections.values():
        service = get_or_create_service(session, data["definition"])
        link = session.scalar(select(AccountService).where(
            AccountService.account_id == account.id,
            AccountService.service_id == service.id,
        ))
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
            for row in session.scalars(select(ScanTrace).where(ScanTrace.account_service_id == link.id))
        }
        signal = sorted(data["signals"])[0] if data["signals"] else "unknown"
        for message_id in data["message_ids"]:
            if message_id and message_id not in existing_ids:
                session.add(ScanTrace(
                    account_service_id=link.id,
                    message_id=message_id,
                    signal_type=signal,
                    signal_value=", ".join(sorted(data["signals"])),
                ))
                existing_ids.add(message_id)
        link.trace_count = len(existing_ids)

    session.commit()


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
    messages_scanned = 0
    estimated_total = 0
    last_persist = 0
    service_limit_reached = False

    try:
        estimated_total = get_message_count(account.email, query=query)
        if progress:
            progress(0, estimated_total, 0)

        for message in iter_message_metadata(account.email, query=query, cancel_check=cancel_check):
            if cancel_check and cancel_check():
                _persist_partial(session, account, detections)
                raise ScanCancelled()

            messages_scanned += 1
            results = detect_message(message, CATALOG)

            for detection in results:
                key = detection.service["name"]
                if key not in detections:
                    if len(detections) >= TEST_SERVICE_LIMIT:
                        service_limit_reached = True
                        break
                    detections[key] = {
                        "definition": detection.service,
                        "score": detection.score,
                        "signals": set(detection.signals),
                        "count": 0,
                        "message_ids": [],
                    }

                item = detections[key]
                item["score"] = max(item["score"], detection.score)
                item["signals"].update(detection.signals)
                item["count"] += 1
                message_id = message.get("id", "")
                if message_id and message_id not in item["message_ids"]:
                    item["message_ids"].append(message_id)

                if detection_callback:
                    detection_callback({
                        "account_id": account.id,
                        "account_email": account.email,
                        "name": item["definition"]["name"],
                        "service_id": item["definition"].get("name"),
                        "category": item["definition"].get("category", "Autre"),
                        "score": item["score"],
                        "count": item["count"],
                        "signals": sorted(item["signals"]),
                    })

            if messages_scanned - last_persist >= 50:
                _persist_partial(session, account, detections)
                last_persist = messages_scanned

            if progress:
                progress(messages_scanned, estimated_total, len(detections))

            if service_limit_reached:
                break

        _persist_partial(session, account, detections)
        account.last_scan_at = datetime.now(timezone.utc)
        history.finished_at = datetime.now(timezone.utc)
        history.status = "completed"
        history.messages_scanned = messages_scanned
        history.services_detected = len(detections)
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
