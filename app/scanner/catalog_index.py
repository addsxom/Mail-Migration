"""Indexes the built-in service catalog for fast message detection."""

from collections import defaultdict

from app.services.builtin_catalog import CATALOG


def _norm(value):
    return (value or "").strip().casefold()


def _sender_domain(sender):
    sender = _norm(sender)
    if "@" not in sender:
        return ""
    return sender.rsplit("@", 1)[1]


class CatalogIndex:
    """Fast candidate lookup for catalog definitions.

    The index supports optional aliases and sender display names while keeping
    the actual verification in detector.py. Domain candidates also include
    subdomains, e.g. mail.example.com -> example.com.
    """

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
        sender_norm = _norm(sender)
        domain = _sender_domain(sender_norm)
        subject_norm = _norm(subject)
        display_name = ""
        if "<" in sender_norm:
            display_name = sender_norm.split("<", 1)[0].strip().strip('"')

        found = {}

        for definition in self.by_domain.get(domain, []):
            found[id(definition)] = definition

        # Subdomains are valid candidates too (e.g. txn.example.com).
        if domain:
            for configured_domain, definitions in self.domain_entries:
                if domain.endswith("." + configured_domain):
                    for definition in definitions if isinstance(definitions, list) else [definitions]:
                        found[id(definition)] = definition

        for definition in self.by_sender.get(sender_norm, []):
            found[id(definition)] = definition
        for name, definitions in self.by_sender_name.items():
            if name and name in display_name:
                for definition in definitions:
                    found[id(definition)] = definition

        # Candidate lookup intentionally remains cheap; final word-boundary
        # verification happens in detector.py.
        for token, definitions in self.by_keyword.items():
            if token in subject_norm:
                for definition in definitions:
                    found[id(definition)] = definition
        for token, definitions in self.by_name.items():
            if token in subject_norm:
                for definition in definitions:
                    found[id(definition)] = definition

        return list(found.values())
