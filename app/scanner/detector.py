"""Service detection rules used by the Gmail scanner."""

import re
from email.utils import parseaddr

from app.scanner.catalog_index import CatalogIndex
from app.scanner.scorer import calculate_score


class Detection:
    def __init__(self, service, score, signals, reliability=None):
        self.service = service
        self.score = score
        self.signals = signals
        self.reliability = reliability or {}


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
    return bool(message_domain) and (message_domain == domain or message_domain.endswith("." + domain))


def _contains_term(text, term):
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
    if address and address in configured:
        return True
    return any("@" not in value and _contains_term(display_name, value) for value in configured)


def detect_message(message, service_definitions=None, catalog_index=None):
    """Detect catalog services and expose source-reliability details.

    Authentication-Results is treated as supporting context only. Its absence
    is not evidence of fraud, and it does not alter the service score yet.
    """
    headers = {
        h.get("name", "").casefold(): h.get("value", "")
        for h in message.get("payload", {}).get("headers", [])
        if h.get("name")
    }
    sender = headers.get("from", "")
    subject = headers.get("subject", "")
    domain = _domain_from_sender(sender)
    auth_results = _normalise(headers.get("authentication-results", ""))

    if catalog_index is None:
        catalog_index = CatalogIndex(service_definitions)

    definitions = catalog_index.candidates(sender, subject)
    results = []

    for definition in definitions:
        signals = []
        domain_match = any(_domain_matches(domain, configured) for configured in definition.get("domains", []))
        sender_match = _sender_matches(sender, definition)
        subject_match = bool(definition.get("name")) and _contains_term(subject, definition["name"])
        keyword_match = any(_contains_term(subject, keyword) for keyword in definition.get("keywords", []))

        if domain_match:
            signals.append("domain")
        if sender_match:
            signals.append("sender")
        if subject_match:
            signals.append("subject")
        if keyword_match:
            signals.append("keyword")

        if not signals:
            continue

        reliability = {
            "spf": "spf=pass" in auth_results if auth_results else None,
            "dkim": "dkim=pass" in auth_results if auth_results else None,
            "dmarc": "dmarc=pass" in auth_results if auth_results else None,
            "official_domain": domain_match,
            "known_sender": sender_match,
        }
        checks = [reliability[k] for k in ("spf", "dkim", "dmarc") if reliability[k] is not None]
        reliability["authentication_available"] = bool(checks)
        reliability["authentication_passed"] = bool(checks) and all(checks)

        results.append(Detection(
            definition,
            calculate_score(signals),
            signals,
            reliability=reliability,
        ))

    return sorted(results, key=lambda detection: detection.score, reverse=True)
