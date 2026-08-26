import json
from email.utils import parseaddr
from app.scanner.scorer import calculate_score

class Detection:
    def __init__(self, service, score, signals):
        self.service = service
        self.score = score
        self.signals = signals

def _domain_from_sender(sender):
    address = parseaddr(sender or "")[1].lower()
    return address.split("@", 1)[1] if "@" in address else ""

def detect_message(message, service_definitions):
    headers = {
        h.get("name", "").lower(): h.get("value", "")
        for h in message.get("payload", {}).get("headers", [])
    }
    sender = headers.get("from", "")
    subject = headers.get("subject", "")
    domain = _domain_from_sender(sender)

    results = []

    for definition in service_definitions:
        signals = []

        if domain and domain in {d.lower() for d in definition.get("domains", [])}:
            signals.append("domain")

        senders = {s.lower() for s in definition.get("senders", [])}
        if sender.lower() in senders or any(s in sender.lower() for s in senders):
            signals.append("sender")

        subject_lower = subject.lower()
        name_lower = definition["name"].lower()
        if name_lower in subject_lower:
            signals.append("subject")

        if any(k.lower() in subject_lower for k in definition.get("keywords", [])):
            signals.append("keyword")

        if signals:
            results.append(Detection(definition, calculate_score(signals), signals))

    return sorted(results, key=lambda x: x.score, reverse=True)
