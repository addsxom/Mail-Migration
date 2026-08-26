from email.utils import parseaddr

from app.scanner.catalog_index import CatalogIndex
from app.scanner.scorer import calculate_score


class Detection:
    def __init__(self, service, score, signals):
        self.service = service
        self.score = score
        self.signals = signals


def _domain_from_sender(sender):
    address = parseaddr(sender or "")[1].lower()
    return address.split("@", 1)[1] if "@" in address else ""


def _domain_matches(message_domain, configured_domain):
    domain = (configured_domain or "").lower().strip()
    # Exact domain or a subdomain of a configured service domain.
    return bool(message_domain) and (
        message_domain == domain or message_domain.endswith("." + domain)
    )


def detect_message(message, service_definitions=None, catalog_index=None):
    headers = {
        h.get("name", "").lower(): h.get("value", "")
        for h in message.get("payload", {}).get("headers", [])
    }
    sender = headers.get("from", "")
    subject = headers.get("subject", "")
    domain = _domain_from_sender(sender)

    if catalog_index is None:
        catalog_index = CatalogIndex(service_definitions)

    definitions = catalog_index.candidates(sender, subject)
    results = []
    subject_lower = subject.lower()
    sender_lower = sender.lower()

    for definition in definitions:
        signals = []

        if any(_domain_matches(domain, d) for d in definition.get("domains", [])):
            signals.append("domain")

        senders = {s.lower() for s in definition.get("senders", [])}
        if sender_lower in senders or any(s in sender_lower for s in senders):
            signals.append("sender")

        name_lower = definition.get("name", "").lower()
        if name_lower and name_lower in subject_lower:
            signals.append("subject")

        if any(k.lower() in subject_lower for k in definition.get("keywords", [])):
            signals.append("keyword")

        if signals:
            score = calculate_score(signals)
            results.append(Detection(definition, score, signals))

            # A domain + sender match is already a very strong identification.
            # Do not perform additional candidate work for this definition.

    return sorted(results, key=lambda x: x.score, reverse=True)
