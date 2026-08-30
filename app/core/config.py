from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
TOKENS_DIR = BASE_DIR / "tokens"
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
DATABASE_FILE = DATA_DIR / "mailmigration.db"
LOG_FILE = DATA_DIR / "mailmigration.log"

DATA_DIR.mkdir(exist_ok=True)
TOKENS_DIR.mkdir(exist_ok=True)

APP_NAME = "Mail Migration"
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
]
MAX_MESSAGES_PER_PAGE = 100
