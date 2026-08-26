from app.google.oauth import token_path_for_email
from app.database.database import Base
from app.database.models import GoogleAccount, ScanHistory, AccountService, ScanTrace


def test_token_path_is_account_specific():
    first = token_path_for_email("User.One@gmail.com")
    second = token_path_for_email("user.two@gmail.com")

    assert first.name == "user.one@gmail.com.json"
    assert second.name == "user.two@gmail.com.json"
    assert first != second


def test_phase_two_account_tables_exist():
    assert GoogleAccount.__tablename__ in Base.metadata.tables
    assert AccountService.__tablename__ in Base.metadata.tables
    assert ScanHistory.__tablename__ in Base.metadata.tables
    assert ScanTrace.__tablename__ in Base.metadata.tables
