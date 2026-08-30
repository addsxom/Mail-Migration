DOMAIN_RULES = {
    "hide.me": ("hide.me", "Technologie"),
    "medal.tv": ("Medal", "Streaming"),
    "streamlabs.com": ("Streamlabs", "Streaming"),
    "supercell.com": ("Supercell", "Jeux"),
    "brawlstars.com": ("Brawl Stars", "Jeux"),
    "brawlstarsgame.com": ("Brawl Stars", "Jeux"),
    "guns.lol": ("guns.lol", "Services"),
    "sellhub.com": ("SellHub", "Services"),
    "intelligence-x.com": ("Intelligence X", "Services"),
    "intelligencex.com": ("Intelligence X", "Services"),
    "bitwarden.com": ("Bitwarden", "Sécurité"),
    "bitwarden.eu": ("Bitwarden", "Sécurité"),
    "shein.com": ("SHEIN", "Shopping"),
    "lego.com": ("LEGO", "Shopping"),
    "just-eat.ch": ("Just Eat", "Shopping"),
    "justeat.com": ("Just Eat", "Shopping"),
    "instant-gaming.com": ("Instant Gaming", "Jeux"),
    "ebookers.com": ("ebookers", "Voyage"),
    "hellcase.com": ("Hellcase", "Jeux"),
    "tinder.com": ("Tinder", "Réseaux sociaux"),
    "sony.com": ("Sony", "Technologie"),
    "sony.eu": ("Sony", "Technologie"),
    "mongodb.com": ("MongoDB", "Technologie"),
    "eneba.com": ("Eneba", "Shopping"),
    "chess.com": ("Chess.com", "Loisirs"),
    "bolt.eu": ("Bolt", "Transport"),
    "medal.tv": ("Medal", "Streaming"),
    "supercellstore.com": ("Supercell Store", "Jeux"),
}

NAME_RULES = {
    "hide me": ("hide.me", "Technologie"),
    "medal": ("Medal", "Streaming"),
    "streamlabs": ("Streamlabs", "Streaming"),
    "supercell": ("Supercell", "Jeux"),
    "brawl stars": ("Brawl Stars", "Jeux"),
    "supercell store": ("Supercell Store", "Jeux"),
    "sellhub": ("SellHub", "Services"),
    "intelligence x": ("Intelligence X", "Services"),
    "bitwarden": ("Bitwarden", "Sécurité"),
    "shein": ("SHEIN", "Shopping"),
    "lego": ("LEGO", "Shopping"),
    "just eat": ("Just Eat", "Shopping"),
    "instant gaming": ("Instant Gaming", "Jeux"),
    "ebookers": ("ebookers", "Voyage"),
    "hellcase": ("Hellcase", "Jeux"),
    "tinder": ("Tinder", "Réseaux sociaux"),
    "mongodb": ("MongoDB", "Technologie"),
    "eneba": ("Eneba", "Shopping"),
    "chess.com": ("Chess.com", "Loisirs"),
    "bolt": ("Bolt", "Transport"),
}


def resolve_service(domain, display_name="", subject=""):
    domain = (domain or "").casefold().strip()
    display_name = (display_name or "").casefold().strip()
    subject = (subject or "").casefold().strip()

    for configured, (name, category) in DOMAIN_RULES.items():
        if domain == configured or domain.endswith("." + configured):
            return {
                "name": name,
                "category": category,
                "subcategory": None,
                "domains": [domain],
                "senders": [],
                "keywords": [name],
                "description": "Service identifié automatiquement à partir du domaine ou du nom de l'expéditeur.",
                "unknown": False,
            }

    combined = f"{display_name} {subject}"
    for term, (name, category) in NAME_RULES.items():
        if term and term in combined:
            return {
                "name": name,
                "category": category,
                "subcategory": None,
                "domains": [domain] if domain else [],
                "senders": [],
                "keywords": [term],
                "description": "Service identifié automatiquement à partir des informations du message.",
                "unknown": False,
            }

    return None
