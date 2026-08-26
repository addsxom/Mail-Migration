"""Indexes the built-in service catalog for fast message detection."""

from collections import defaultdict
from app.services.builtin_catalog import CATALOG


def _norm(value):
    return (value or "").strip().lower()


def _sender_domain(sender):
    sender = _norm(sender)
    if "@" not in sender:
        return ""
    return sender.rsplit("@", 1)[1]


class CatalogIndex:
    def __init__(self, definitions=None):
        self.definitions = list(definitions or CATALOG)
        self.by_domain = defaultdict(list)
        self.by_sender = defaultdict(list)
        self.by_keyword = defaultdict(list)
        self.by_name = defaultdict(list)

        for definition in self.definitions:
            for domain in definition.get("domains", []):
                self.by_domain[_norm(domain)].append(definition)
            for sender in definition.get("senders", []):
                self.by_sender[_norm(sender)].append(definition)
            for keyword in definition.get("keywords", []):
                key = _norm(keyword)
                if key:
                    self.by_keyword[key].append(definition)
            name = _norm(definition.get("name"))
            if name:
                self.by_name[name].append(definition)

    def candidates(self, sender="", subject=""):
        sender_norm = _norm(sender)
        domain = _sender_domain(sender_norm)
        subject_norm = _norm(subject)
        found = {}

        for definition in self.by_domain.get(domain, []):
            found[id(definition)] = definition
        for definition in self.by_sender.get(sender_norm, []):
            found[id(definition)] = definition

        # Keyword/name lookup is intentionally indexed by tokens so we do not
        # compare every message against the whole catalog.
        haystack = subject_norm
        for keyword, definitions in self.by_keyword.items():
            if keyword in haystack:
                for definition in definitions:
                    found[id(definition)] = definition
        for name, definitions in self.by_name.items():
            if name in haystack:
                for definition in definitions:
                    found[id(definition)] = definition

        return list(found.values())
