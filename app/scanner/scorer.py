"""Scoring engine for Phase 4.2.

The score estimates how confident Mail Migration is that a message belongs
 to a catalog service. It is NOT a phishing/spam verdict.
"""

WEIGHTS = {
    "domain": 50.0,
    "sender": 25.0,
    "subject": 15.0,
    "keyword": 10.0,
}


def calculate_score(signals):
    """Return a reproducible 0-100 score from unique detection signals."""
    return min(100.0, float(sum(WEIGHTS.get(signal, 0.0) for signal in set(signals))))


def score_details(signals):
    """Return the individual contributions used by the UI."""
    unique = set(signals)
    return [
        {"signal": signal, "weight": WEIGHTS[signal], "matched": signal in unique}
        for signal in ("domain", "sender", "subject", "keyword")
    ]
