import re
from email.utils import parseaddr

from app.scanner.catalog_index import CatalogIndex
from app.scanner.scorer import calculate_score
from app.scanner.intelligent_services import resolve_service


IGNORED_UNKNOWN_DOMAINS = {
    "gmail.com", "googlemail.com", "google.com", "accounts.google.com",
    "googleusercontent.com", "yahoo.com", "yahoo.fr", "hotmail.com",
    "hotmail.fr", "outlook.com", "outlook.fr", "live.com", "live.fr",
    "msn.com", "icloud.com", "me.com", "mac.com", "proton.me",
    "protonmail.com", "gmx.com", "gmx.ch", "bluewin.ch",
}


class Detection:
    def __init__(self, service, score, signals, reliability=None, sender_email=None):
        self.service = service
        self.score = score
        self.signals = signals
        self.reliability = reliability or {}
        self.sender_email = sender_email


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


def _known_domain(domain, definitions):
    return any(_domain_matches(domain, configured) for definition in definitions for configured in definition.get("domains", []))


def _readable_unknown_service_name(sender, domain):
    display_name = _sender_display_name(sender)
    if display_name:
        label = display_name
    else:
        host = domain.split(".", 1)[0] if domain else "Service inconnu"
        label = re.sub(r"[-_]+", " ", host, flags=re.UNICODE)
        label = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", label)
        label = label.strip()
        if label:
            label = label[:1].upper() + label[1:]
    label = re.sub(r"[^\w .&+\-]", "", label, flags=re.UNICODE).strip()
    return (label[:120] or "Service inconnu").strip()


def _unknown_detection(sender, domain, subject, definitions):
    if not domain or domain in IGNORED_UNKNOWN_DOMAINS or _known_domain(domain, definitions):
        return None
    display_name = _sender_display_name(sender)
    label = _readable_unknown_service_name(sender, domain)
    score = 30.0
    if display_name:
        score += 5.0
    if subject and display_name and _contains_term(subject, display_name):
        score += 5.0
    definition = {
        "name": label,
        "category": "Inconnu",
        "subcategory": "Domaine non catalogué",
        "domains": [domain],
        "senders": [_sender_address(sender)] if _sender_address(sender) else [],
        "keywords": [display_name] if display_name else [],
        "description": "Candidat détecté automatiquement à partir d'un domaine absent du catalogue. Vérification manuelle recommandée.",
        "unknown": True,
    }
    reliability = {
        "official_domain": False,
        "known_sender": False,
        "authentication_available": False,
        "spf": None,
        "dkim": None,
        "dmarc": None,
    }
    return Detection(definition, min(45.0, score), ["unknown_domain"], reliability, _sender_address(sender))


def _intelligent_detection(sender, domain, subject):
    definition = resolve_service(domain, _sender_display_name(sender), subject)
    if not definition:
        return None
    return Detection(
        definition,
        75.0,
        ["intelligent_domain" if domain else "intelligent_name"],
        {
            "official_domain": bool(domain),
            "known_sender": False,
            "authentication_available": False,
            "spf": None,
            "dkim": None,
            "dmarc": None,
        },
        _sender_address(sender),
    )


def detect_message(message, service_definitions=None, catalog_index=None):
    headers = {
        h.get("name", "").casefold(): h.get("value", "")
        for h in message.get("payload", {}).get("headers", [])
        if h.get("name")
    }
    sender = headers.get("from", "") or headers.get("reply-to", "")
    sender_email = _sender_address(sender)
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
        checks = [reliability[key] for key in ("spf", "dkim", "dmarc") if reliability[key] is not None]
        reliability["authentication_available"] = bool(checks)
        reliability["authentication_passed"] = bool(checks) and all(checks)
        results.append(Detection(definition, calculate_score(signals), signals, reliability=reliability, sender_email=sender_email))

    if not results:
        intelligent = _intelligent_detection(sender, domain, subject)
        if intelligent:
            results.append(intelligent)

    if not results:
        unknown = _unknown_detection(sender, domain, subject, definitions)
        if unknown:
            results.append(unknown)

    return sorted(results, key=lambda detection: detection.score, reverse=True)
