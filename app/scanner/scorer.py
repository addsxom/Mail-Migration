def calculate_score(signals):
    """
    signals: iterable of signal types.
    Poids volontairement plafonnés pour éviter un score > 100.
    """
    weights = {
        "domain": 45,
        "sender": 30,
        "subject": 15,
        "keyword": 10,
    }
    unique = set(signals)
    score = sum(weights.get(s, 0) for s in unique)
    return min(100.0, float(score))
