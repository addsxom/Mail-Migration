from app.scanner.detector import detect_message

CATALOG = [{
    "name": "Example",
    "category": "Test",
    "domains": ["example.com"],
    "senders": ["noreply@example.com"],
    "keywords": ["Example"],
}]

def test_detects_example():
    message = {
        "id": "1",
        "payload": {
            "headers": [
                {"name": "From", "value": "noreply@example.com"},
                {"name": "Subject", "value": "Example account"},
            ]
        }
    }
    result = detect_message(message, CATALOG)
    assert result
    assert result[0].service["name"] == "Example"
    assert result[0].score == 100
