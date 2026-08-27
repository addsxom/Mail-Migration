"""Service detection rules used by the Gmail scanner.

Phase 4.1 improves the signals used to identify services. The score formula
itself is intentionally unchanged for Phase 4.2.
"""

import re
from email.utils import parseaddr

from app.scanner.catalog_index import CatalogIndex
from app.scanner.scorer import calculate_score


class Detection:
    def __init__(self, service, score, signals):
        self.service = service
        self.score = score
        self.signals = signals


def _normalise(value):
    value = value or ""
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _domain_from_sender(sender):
    address = parseaddr(sender or "")[1].casefold()
    return address.split("@", 1)[1] if "@" in address else ""


def _sender_address(sender):
    return parseaddr(sender or "")[1].casefold().strip()


def _sender_display_name(sender):
    return _normalise(parseaddr(sender or "")[0])


def _domain_matches(message_domain, configured_domain):
    domain = _normalise(configured_domain)
    return bool(message_domain) and (
        message_domain == domain or message_domain.endswith("." + domain)
    )


def _contains_term(text, term):
    """Match a complete word/phrase, avoiding accidental substring matches."""
    text = _normalise(text)
    term = _normalise(term)
    if not text or not term:
        return False
    pattern = r"(?<![\w])" + re.escape(term) + r"(?![\w])"
    return re.search(pattern, text, flags=re.UNICODE) is not None


def _sender_matches(sender, definition):
    address = _sender_address(sender)
    display_name = _sender_display_name(sender)
    configured = [_normalise(value) for value in definition.get("senders", []) if value]

    # Email senders must match exactly. Display-name rules are supported when
    # a catalog entry intentionally contains a name rather than an address.
    if address and address in configured:
        return True
    return any("@" not in value and _contains_term(display_name, value)
               for value in configured)


def detect_message(message, service_definitions=None, catalog_index=None):
    """Detect catalog services using domain, sender, subject and keywords.

    Phase 4.1 deliberately keeps the existing signal names so the current
    scorer remains compatible. It improves matching precision by normalising
    text and using complete-word/phrase matching instead of loose substrings.
    """
    headers = {
        h.get("name", "").casefold(): h.get("value", "")
        for h in message.get("payload", {}).get("headers", [])
        if h.get("name")
    }
    sender = headers.get("from", "")
    subject = headers.get("subject", "")
    domain = _domain_from_sender(sender)

    if catalog_index is None:
        catalog_index = CatalogIndex(service_definitions)

    definitions = catalog_index.candidates(sender, subject)
    results = []

    for definition in definitions:
        signals = []

        if any(_domain_matches(domain, configured)
               for configured in definition.get("domains", [])):
            signals.append("domain")

        if _sender_matches(sender, definition):
            signals.append("sender")

        service_name = definition.get("name", "")
        if service_name and _contains_term(subject, service_name):
            signals.append("subject")

        if any(_contains_term(subject, keyword)
               for keyword in definition.get("keywords", [])):
            signals.append("keyword")

        if signals:
            score = calculate_score(signals)
            results.append(Detection(definition, score, signals))

    return sorted(results, key=lambda detection: detection.score, reverse=True)
