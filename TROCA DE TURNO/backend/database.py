import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import (
    BACKUP_DIR,
    BACKUP_RETENTION_DAYS,
    DATA_DIR,
    DB_BUSY_TIMEOUT_MS,
    DB_PATH,
    SESSION_TTL_SECONDS,
)
from .security import hash_password, new_session_token, token_digest, verify_password


class UnitConflictError(Exception):
    def __init__(self, current: dict[str, Any]):
        super().__init__("Esta unidade foi atualizada por outro usuário.")
        self.current = current


ALLOWED_UNIT_CODES = ("PPT", "NRD", "RBR", "PST")
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ALLOWED_ROLES = {ROLE_ADMIN, ROLE_USER}


def _validate_unit(unit: dict[str, Any], position: int) -> tuple[str, str]:
    code = str(unit.get("code", "")).strip().upper()
    name = str(unit.get("name", "")).strip()
    if code not in ALLOWED_UNIT_CODES or not name:
        raise ValueError("Unidade inválida.")
    if position < 0 or position >= len(ALLOWED_UNIT_CODES):
        raise ValueError("Posição da unidade inválida.")
    return code, name


@contextmanager
def connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=max(DB_BUSY_TIMEOUT_MS / 1000, 1))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {DB_BUSY_TIMEOUT_MS}")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def init_db() -> None:
    with connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                position INTEGER NOT NULL,
                data_json TEXT NOT NULL,
                updated_by INTEGER,
                updated_at INTEGER NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS unit_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_code TEXT NOT NULL,
                unit_name TEXT NOT NULL,
                user_id INTEGER,
                action TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
            CREATE INDEX IF NOT EXISTS idx_units_position ON units(position);
            CREATE INDEX IF NOT EXISTS idx_unit_history_code_created ON unit_history(unit_code, created_at DESC);
            """
        )
        if not _column_exists(conn, "users", "role"):
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        if not _column_exists(conn, "users", "is_active"):
            conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if not _column_exists(conn, "units", "version"):
            conn.execute("ALTER TABLE units ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
        conn.execute("UPDATE users SET role = 'user' WHERE role IS NULL OR role NOT IN ('admin', 'user')")
        conn.execute("UPDATE users SET is_active = 1 WHERE is_active IS NULL")
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))


def create_backup(force: bool = False) -> Path | None:
    if not DB_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    day_prefix = f"posicao_campo-{now:%Y-%m-%d}"
    existing = sorted(BACKUP_DIR.glob(f"{day_prefix}*.db"))
    if existing and not force:
        _cleanup_old_backups(now)
        return existing[-1]

    suffix = f"-{now:%H%M%S}" if force or existing else ""
    destination = BACKUP_DIR / f"{day_prefix}{suffix}.db"
    source = sqlite3.connect(DB_PATH, timeout=max(DB_BUSY_TIMEOUT_MS / 1000, 1))
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    _cleanup_old_backups(now)
    return destination


def _cleanup_old_backups(now: datetime | None = None) -> None:
    if not BACKUP_DIR.exists():
        return
    cutoff = (now or datetime.now()) - timedelta(days=BACKUP_RETENTION_DAYS)
    for backup in BACKUP_DIR.glob("posicao_campo-*.db"):
        try:
            modified = datetime.fromtimestamp(backup.stat().st_mtime)
            if modified < cutoff:
                backup.unlink(missing_ok=True)
        except OSError:
            continue


def _validate_credentials(name: str, password: str) -> tuple[str, str]:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("Informe o nome do usuário.")
    if password == "":
        raise ValueError("Informe a senha.")
    if len(cleaned_name) > 80:
        raise ValueError("O nome do usuário deve ter no máximo 80 caracteres.")
    if len(password) > 256:
        raise ValueError("A senha deve ter no máximo 256 caracteres.")
    return cleaned_name, password


def _user_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "role": row["role"] if row["role"] in ALLOWED_ROLES else ROLE_USER,
        "is_active": bool(row["is_active"]),
        "created_at": int(row["created_at"] or 0),
    }


def create_user(name: str, password: str) -> dict[str, Any]:
    cleaned_name, password = _validate_credentials(name, password)
    now = int(time.time())
    with connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (name, password_hash, role, is_active, created_at) VALUES (?, ?, 'user', 1, ?)",
                (cleaned_name, hash_password(password), now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Este nome de usuário já está cadastrado.") from exc
        row = conn.execute(
            "SELECT id, name, role, is_active, created_at FROM users WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return _user_payload(row)


def create_or_update_admin(name: str, password: str) -> dict[str, Any]:
    cleaned_name, password = _validate_credentials(name, password)
    password_hash = hash_password(password)
    now = int(time.time())
    with connection() as conn:
        existing_target = conn.execute(
            "SELECT id FROM users WHERE name = ? COLLATE NOCASE",
            (cleaned_name,),
        ).fetchone()
        previous_admins = conn.execute(
            "SELECT id FROM users WHERE role = 'admin'"
        ).fetchall()

        if existing_target:
            user_id = int(existing_target["id"])
        else:
            cursor = conn.execute(
                "INSERT INTO users (name, password_hash, role, is_active, created_at) VALUES (?, ?, 'user', 1, ?)",
                (cleaned_name, password_hash, now),
            )
            user_id = int(cursor.lastrowid)

        # Mantém apenas um Administrador configurado pelo utilitário local.
        conn.execute("UPDATE users SET role = 'user' WHERE role = 'admin' AND id <> ?", (user_id,))
        conn.execute(
            "UPDATE users SET name = ?, password_hash = ?, role = 'admin', is_active = 1 WHERE id = ?",
            (cleaned_name, password_hash, user_id),
        )

        affected_ids = {int(row["id"]) for row in previous_admins}
        affected_ids.add(user_id)
        for affected_id in affected_ids:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (affected_id,))

        result = conn.execute(
            "SELECT id, name, role, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return _user_payload(result)

def has_admin() -> bool:
    with connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE role = 'admin' AND is_active = 1 LIMIT 1"
        ).fetchone()
    return bool(row)


def list_users() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, name, role, is_active, created_at FROM users ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, name COLLATE NOCASE ASC, id ASC"
        ).fetchall()
    return [_user_payload(row) for row in rows]


def _editable_user(conn: sqlite3.Connection, user_id: int, current_user_id: int) -> sqlite3.Row:
    if user_id == current_user_id:
        raise ValueError("Você não pode alterar a própria conta por esta tela.")
    row = conn.execute(
        "SELECT id, name, role, is_active FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        raise ValueError("Usuário não encontrado.")
    if row["role"] == ROLE_ADMIN:
        raise ValueError("A conta de Administrador não pode ser alterada por esta tela.")
    return row


def delete_user(user_id: int, current_user_id: int) -> None:
    with connection() as conn:
        _editable_user(conn, user_id, current_user_id)
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def set_user_active(user_id: int, is_active: bool, current_user_id: int) -> dict[str, Any]:
    with connection() as conn:
        _editable_user(conn, user_id, current_user_id)
        active_value = 1 if is_active else 0
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (active_value, user_id))
        if not is_active:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        row = conn.execute(
            "SELECT id, name, role, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return _user_payload(row)


def reset_user_password(user_id: int, password: str, current_user_id: int) -> None:
    if password == "":
        raise ValueError("Informe a nova senha.")
    if len(password) > 256:
        raise ValueError("A senha deve ter no máximo 256 caracteres.")
    with connection() as conn:
        _editable_user(conn, user_id, current_user_id)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def authenticate_user(name: str, password: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT id, name, password_hash, role, is_active, created_at FROM users WHERE name = ? COLLATE NOCASE",
            (name.strip(),),
        ).fetchone()
    if not row or not bool(row["is_active"]) or not verify_password(password, row["password_hash"]):
        return None
    return _user_payload(row)


def create_session(user_id: int) -> str:
    token = new_session_token()
    now = int(time.time())
    with connection() as conn:
        conn.execute(
            "INSERT INTO sessions (user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (user_id, token_digest(token), now + SESSION_TTL_SECONDS, now),
        )
    return token


def get_user_by_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    now = int(time.time())
    digest = token_digest(token)
    with connection() as conn:
        row = conn.execute(
            """
            SELECT users.id, users.name, users.role, users.is_active, users.created_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ? AND users.is_active = 1
            """,
            (digest, now),
        ).fetchone()
    return _user_payload(row) if row else None


def delete_session(token: str | None) -> None:
    if not token:
        return
    with connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest(token),))


def _decode_unit(row: sqlite3.Row) -> dict[str, Any] | None:
    try:
        return json.loads(row["data_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def list_units_payload() -> dict[str, Any]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT u.data_json, u.version, u.updated_at, u.updated_by, users.name AS updated_by_name
            FROM units u
            LEFT JOIN users ON users.id = u.updated_by
            ORDER BY u.position ASC, u.id ASC
            """
        ).fetchall()

    units: list[dict[str, Any]] = []
    meta: dict[str, dict[str, Any]] = {}
    for row in rows:
        unit = _decode_unit(row)
        if not unit:
            continue
        code = str(unit.get("code", "")).strip().upper()
        units.append(unit)
        if code:
            meta[code] = {
                "version": int(row["version"] or 1),
                "updated_at": int(row["updated_at"] or 0),
                "updated_by": row["updated_by_name"] or "-",
            }
    return {"units": units, "meta": meta}


def list_units() -> list[dict[str, Any]]:
    return list_units_payload()["units"]


def _history_insert(
    conn: sqlite3.Connection,
    *,
    unit_code: str,
    unit_name: str,
    user_id: int,
    action: str,
    before_json: str | None,
    after_json: str,
    version: int,
    created_at: int,
) -> None:
    conn.execute(
        """
        INSERT INTO unit_history (
            unit_code, unit_name, user_id, action, before_json, after_json, version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (unit_code, unit_name, user_id, action, before_json, after_json, version, created_at),
    )


def initialize_units(units: list[dict[str, Any]], user_id: int) -> dict[str, Any]:
    now = int(time.time())
    with connection() as conn:
        existing = conn.execute("SELECT COUNT(*) AS total FROM units").fetchone()["total"]
        if existing:
            return list_units_payload()

        for position, unit in enumerate(units):
            try:
                code, name = _validate_unit(unit, position)
            except ValueError:
                continue
            payload = json.dumps(unit, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO units (code, name, position, data_json, updated_by, updated_at, version)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (code, name, position, payload, user_id, now),
            )
            _history_insert(
                conn,
                unit_code=code,
                unit_name=name,
                user_id=user_id,
                action="criação",
                before_json=None,
                after_json=payload,
                version=1,
                created_at=now,
            )
    return list_units_payload()


def save_unit(
    unit: dict[str, Any],
    position: int,
    user_id: int,
    expected_version: int | None = None,
) -> dict[str, Any]:
    code, name = _validate_unit(unit, position)

    now = int(time.time())
    payload = json.dumps(unit, ensure_ascii=False)
    with connection() as conn:
        # Serializa as gravações antes da leitura da versão para impedir
        # que duas edições concorrentes validem a mesma versão ao mesmo tempo.
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT u.data_json, u.version, u.updated_at, users.name AS updated_by_name
            FROM units u
            LEFT JOIN users ON users.id = u.updated_by
            WHERE u.code = ?
            """,
            (code,),
        ).fetchone()

        if row:
            current_version = int(row["version"] or 1)
            if expected_version is not None and expected_version != current_version:
                current_unit = _decode_unit(row) or unit
                raise UnitConflictError(
                    {
                        "unit": current_unit,
                        "meta": {
                            "version": current_version,
                            "updated_at": int(row["updated_at"] or 0),
                            "updated_by": row["updated_by_name"] or "-",
                        },
                    }
                )
            new_version = current_version + 1
            before_json = row["data_json"]
            conn.execute(
                """
                UPDATE units
                SET name = ?, position = ?, data_json = ?, updated_by = ?, updated_at = ?, version = ?
                WHERE code = ?
                """,
                (name, position, payload, user_id, now, new_version, code),
            )
            action = "atualização"
        else:
            new_version = 1
            before_json = None
            conn.execute(
                """
                INSERT INTO units (code, name, position, data_json, updated_by, updated_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (code, name, position, payload, user_id, now, new_version),
            )
            action = "criação"

        _history_insert(
            conn,
            unit_code=code,
            unit_name=name,
            user_id=user_id,
            action=action,
            before_json=before_json,
            after_json=payload,
            version=new_version,
            created_at=now,
        )

        user_name = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
        updated_by = user_name["name"] if user_name else "-"

    return {
        "unit": unit,
        "meta": {"version": new_version, "updated_at": now, "updated_by": updated_by},
    }


def list_history(limit: int = 100, unit_code: str | None = None) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit), 1), 300)
    params: list[Any] = []
    where = ""
    if unit_code:
        where = "WHERE h.unit_code = ?"
        params.append(unit_code.strip().upper())
    params.append(safe_limit)

    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT h.id, h.unit_code, h.unit_name, h.action, h.version, h.created_at,
                   users.name AS user_name
            FROM unit_history h
            LEFT JOIN users ON users.id = h.user_id
            {where}
            ORDER BY h.created_at DESC, h.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return [
        {
            "id": row["id"],
            "unit_code": row["unit_code"],
            "unit_name": row["unit_name"],
            "action": row["action"],
            "version": row["version"],
            "created_at": row["created_at"],
            "user_name": row["user_name"] or "Usuário removido",
        }
        for row in rows
    ]
