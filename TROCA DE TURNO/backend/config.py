from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "posicao_campo.db"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_RETENTION_DAYS = 30
SESSION_COOKIE = "posicao_campo_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
MAX_BODY_BYTES = 2 * 1024 * 1024
DB_BUSY_TIMEOUT_MS = 10_000
