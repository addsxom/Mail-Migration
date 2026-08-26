from app.database.database import Base
from app.database.models import GoogleAccount, Service

def test_models_exist():
    assert GoogleAccount.__tablename__ == "google_accounts"
    assert Service.__tablename__ == "services"
    assert "google_accounts" in Base.metadata.tables
