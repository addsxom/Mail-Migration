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


def test_detects_unknown_domain():
    message = {
        "id": "2",
        "payload": {
            "headers": [
                {"name": "From", "value": "Example Service <noreply@unknown-service.test>"},
                {"name": "Subject", "value": "Welcome to Example Service"},
            ]
        }
    }
    result = detect_message(message, CATALOG)
    unknown = [item for item in result if item.service.get("unknown")]
    assert unknown
    assert unknown[0].service["name"] == "Inconnu — unknown-service.test"
    assert "unknown_domain" in unknown[0].signals


def test_ignores_free_mail_provider_as_unknown():
    message = {
        "id": "3",
        "payload": {
            "headers": [
                {"name": "From", "value": "Someone <person@gmail.com>"},
                {"name": "Subject", "value": "Hello"},
            ]
        }
    }
    result = detect_message(message, CATALOG)
    assert not [item for item in result if item.service.get("unknown")]
