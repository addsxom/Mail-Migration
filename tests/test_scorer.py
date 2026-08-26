from app.scanner.scorer import calculate_score

def test_domain_and_sender():
    assert calculate_score(["domain", "sender"]) == 75

def test_score_is_capped():
    assert calculate_score(["domain", "sender", "subject", "keyword"]) == 100
