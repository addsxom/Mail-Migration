from collections import defaultdict
from email.utils import parseaddr

from app.services.builtin_catalog import CATALOG
from app.services.extended_catalog import EXTRA_CATALOG

CATALOG = CATALOG + EXTRA_CATALOG

def _norm(value):
    return (value or "").strip().casefold()

def _sender_address(sender):
    return parseaddr(sender or "")[1].casefold().strip()

def _sender_domain(sender):
    address = _sender_address(sender)
    return address.rsplit("@", 1)[1] if "@" in address else ""

def _sender_display_name(sender):
    return _norm(parseaddr(sender or "")[0])

class CatalogIndex:
    def __init__(self, definitions=None):
        self.definitions = list(definitions or CATALOG)
        self.by_domain = defaultdict(list)
        self.by_sender = defaultdict(list)
        self.by_sender_name = defaultdict(list)
        self.by_keyword = defaultdict(list)
        self.by_name = defaultdict(list)
        self.domain_entries = []
        for definition in self.definitions:
            for domain in definition.get("domains", []):
                key = _norm(domain)
                if key:
                    self.by_domain[key].append(definition)
                    self.domain_entries.append((key, definition))
            for sender in definition.get("senders", []):
                key = _norm(sender)
                if not key:
                    continue
                if "@" in key:
                    self.by_sender[key].append(definition)
                else:
                    self.by_sender_name[key].append(definition)
            for alias in definition.get("aliases", []):
                key = _norm(alias)
                if key:
                    self.by_name[key].append(definition)
            for keyword in definition.get("keywords", []):
                key = _norm(keyword)
                if key:
                    self.by_keyword[key].append(definition)
            name = _norm(definition.get("name"))
            if name:
                self.by_name[name].append(definition)

    def candidates(self, sender="", subject=""):
        sender_address = _sender_address(sender)
        domain = _sender_domain(sender)
        subject_norm = _norm(subject)
        display_name = _sender_display_name(sender)
        found = {}
        for definition in self.by_domain.get(domain, []):
            found[id(definition)] = definition
        if domain:
            for configured_domain, definition in self.domain_entries:
                if domain == configured_domain or domain.endswith("." + configured_domain):
                    found[id(definition)] = definition
        for definition in self.by_sender.get(sender_address, []):
            found[id(definition)] = definition
        if display_name:
            for name, definitions in self.by_sender_name.items():
                if name and name in display_name:
                    for definition in definitions:
                        found[id(definition)] = definition
        for token, definitions in self.by_keyword.items():
            if token in subject_norm:
                for definition in definitions:
                    found[id(definition)] = definition
        for token, definitions in self.by_name.items():
            if token in subject_norm:
                for definition in definitions:
                    found[id(definition)] = definition
        return list(found.values())
