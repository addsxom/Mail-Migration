from datetime import datetime, timezone
from sqlalchemy import select
from app.database.models import GoogleAccount, AccountService, ScanHistory, ScanTrace
from app.database.repositories import get_or_create_service
from app.google.gmail import iter_message_metadata
from app.services.builtin_catalog import CATALOG
from .detector import detect_message

class ScanCancelled(Exception):
    pass

def scan_account(session, account_id, progress=None, cancel_check=None):
    account = session.get(GoogleAccount, account_id)
    if not account:
        raise ValueError("Compte introuvable.")

    history = ScanHistory(account_id=account.id, status="running")
    session.add(history)
    session.commit()

    detections = {}
    messages_scanned = 0

    try:
        for message in iter_message_metadata(
            account.email,
            cancel_check=cancel_check,
        ):
            if cancel_check and cancel_check():
                raise ScanCancelled()

            messages_scanned += 1
            results = detect_message(message, CATALOG)

            for detection in results:
                key = detection.service["name"]
                if key not in detections:
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
                item["message_ids"].append(message.get("id", ""))

            if progress:
                progress(messages_scanned, len(detections))

        for data in detections.values():
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
                    trace_count=data["count"],
                    first_detected_at=now,
                    last_detected_at=now,
                    status="À vérifier",
                )
                session.add(link)
                session.flush()
            else:
                link.confidence_score = max(link.confidence_score, data["score"])
                link.trace_count += data["count"]
                link.last_detected_at = now

            for message_id in data["message_ids"]:
                signal = next(iter(data["signals"]), "unknown")
                session.add(
                    ScanTrace(
                        account_service_id=link.id,
                        message_id=message_id,
                        signal_type=signal,
                        signal_value=", ".join(sorted(data["signals"])),
                    )
                )

        account.last_scan_at = datetime.now(timezone.utc)
        history.finished_at = datetime.now(timezone.utc)
        history.status = "completed"
        history.messages_scanned = messages_scanned
        history.services_detected = len(detections)
        session.commit()
        return messages_scanned, len(detections)

    except ScanCancelled:
        history.finished_at = datetime.now(timezone.utc)
        history.status = "cancelled"
        history.messages_scanned = messages_scanned
        session.commit()
        raise

    except Exception as exc:
        session.rollback()
        history = session.get(ScanHistory, history.id)
        if history:
            history.finished_at = datetime.now(timezone.utc)
            history.status = "error"
            history.messages_scanned = messages_scanned
            history.error = str(exc)
            session.commit()
        raise
