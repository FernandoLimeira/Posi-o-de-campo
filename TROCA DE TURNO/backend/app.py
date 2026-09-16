import json
import mimetypes
import threading
import time
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

from .config import BASE_DIR, MAX_BODY_BYTES, SESSION_COOKIE, SESSION_TTL_SECONDS
from .database import (
    UnitConflictError,
    authenticate_user,
    create_backup,
    create_session,
    create_user,
    delete_user,
    delete_session,
    reset_user_password,
    set_user_active,
    get_user_by_session,
    init_db,
    initialize_units,
    list_history,
    list_users,
    list_units_payload,
    save_unit,
)

STATIC_ROOTS = {"css", "js", "assets"}
LOGIN_WINDOW_SECONDS = 5 * 60
LOGIN_MAX_FAILURES = 10
_login_failures = {}
_login_lock = threading.Lock()


def _client_key(environ, username=""):
    return (environ.get("REMOTE_ADDR", "unknown"), username.strip().casefold())


def _login_blocked(environ, username):
    key = _client_key(environ, username)
    now = time.time()
    with _login_lock:
        attempts = [stamp for stamp in _login_failures.get(key, []) if now - stamp < LOGIN_WINDOW_SECONDS]
        if attempts:
            _login_failures[key] = attempts
        else:
            _login_failures.pop(key, None)
        return len(attempts) >= LOGIN_MAX_FAILURES


def _record_login_failure(environ, username):
    key = _client_key(environ, username)
    now = time.time()
    with _login_lock:
        attempts = [stamp for stamp in _login_failures.get(key, []) if now - stamp < LOGIN_WINDOW_SECONDS]
        attempts.append(now)
        _login_failures[key] = attempts[-LOGIN_MAX_FAILURES:]


def _clear_login_failures(environ, username):
    with _login_lock:
        _login_failures.pop(_client_key(environ, username), None)


def _same_origin_request(environ):
    origin = environ.get("HTTP_ORIGIN")
    if not origin:
        return True
    host = environ.get("HTTP_HOST", "")
    if not host:
        return False
    return origin in {f"http://{host}", f"https://{host}"}



def _cookies(environ):
    raw = environ.get("HTTP_COOKIE", "")
    cookies = {}
    for part in raw.split(";"):
        if "=" in part:
            key, value = part.strip().split("=", 1)
            cookies[key] = value
    return cookies


def _session_user(environ):
    return get_user_by_session(_cookies(environ).get(SESSION_COOKIE))


def _is_admin(user):
    return bool(user and user.get("role") == "admin" and user.get("is_active", True))


def _json_body(environ):
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length < 0:
        raise ValueError("Tamanho de requisição inválido.")
    if length > MAX_BODY_BYTES:
        raise ValueError("Requisição muito grande.")
    body = environ["wsgi.input"].read(length) if length else b"{}"
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("JSON inválido.") from exc
    return payload


def _respond(start_response, status, body=b"", headers=None):
    headers = list(headers or [])
    headers.append(("Content-Length", str(len(body))))
    headers.append(("X-Content-Type-Options", "nosniff"))
    headers.append(("X-Frame-Options", "DENY"))
    headers.append(("Referrer-Policy", "no-referrer"))
    headers.append(("Permissions-Policy", "camera=(), microphone=(), geolocation=()"))
    headers.append(("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"))
    start_response(f"{status.value} {status.phrase}", headers)
    return [body]


def _json(start_response, status, payload, headers=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    all_headers = [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store")]
    all_headers.extend(headers or [])
    return _respond(start_response, status, body, all_headers)


def _redirect(start_response, location):
    return _respond(start_response, HTTPStatus.FOUND, b"", [("Location", location), ("Cache-Control", "no-store")])


def _file(start_response, path: Path):
    if not path.is_file():
        return _respond(start_response, HTTPStatus.NOT_FOUND, "Arquivo não encontrado.".encode("utf-8"))
    mime, _ = mimetypes.guess_type(str(path))
    data = path.read_bytes()
    content_type = f"{mime}; charset=utf-8" if (mime or "").startswith("text/") else (mime or "application/octet-stream")
    cache_control = "no-store" if path.suffix in {".html", ".js"} else "public, max-age=3600"
    return _respond(
        start_response,
        HTTPStatus.OK,
        data,
        [("Content-Type", content_type), ("Cache-Control", cache_control)],
    )


def _auth_cookie(token):
    return (
        "Set-Cookie",
        f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL_SECONDS}",
    )


def _clear_auth_cookie():
    return (
        "Set-Cookie",
        f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
    )


def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/")
    query = parse_qs(environ.get("QUERY_STRING", ""))
    user = _session_user(environ)

    if method in {"POST", "PUT", "PATCH", "DELETE"} and not _same_origin_request(environ):
        return _json(start_response, HTTPStatus.FORBIDDEN, {"error": "Origem da requisição não permitida."})

    if path == "/login" and method == "GET":
        if user:
            return _redirect(start_response, "/")
        return _file(start_response, BASE_DIR / "login.html")

    if path == "/register" and method == "GET":
        return _redirect(start_response, "/login")

    if path == "/api/auth/register" and method == "POST":
        return _json(start_response, HTTPStatus.NOT_FOUND, {"error": "Cadastro público desativado."})

    if path == "/api/auth/login" and method == "POST":
        try:
            payload = _json_body(environ)
        except ValueError as exc:
            return _json(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        username = str(payload.get("name", ""))
        password = str(payload.get("password", ""))
        if _login_blocked(environ, username):
            return _json(start_response, HTTPStatus.TOO_MANY_REQUESTS, {"error": "Muitas tentativas de login. Aguarde alguns minutos."})
        logged = authenticate_user(username, password)
        if not logged:
            _record_login_failure(environ, username)
            return _json(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Nome ou senha inválidos."})
        _clear_login_failures(environ, username)
        token = create_session(logged["id"])
        return _json(start_response, HTTPStatus.OK, {"user": logged}, [_auth_cookie(token)])

    if path == "/api/auth/logout" and method == "POST":
        token = _cookies(environ).get(SESSION_COOKIE)
        delete_session(token)
        return _json(start_response, HTTPStatus.OK, {"ok": True}, [_clear_auth_cookie()])

    if path == "/api/auth/me" and method == "GET":
        if not user:
            return _json(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Sessão expirada."})
        return _json(start_response, HTTPStatus.OK, {"user": user})


    if path == "/api/users" and method == "GET":
        if not user:
            return _json(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Autenticação necessária."})
        if not _is_admin(user):
            return _json(start_response, HTTPStatus.FORBIDDEN, {"error": "Acesso exclusivo do Administrador."})
        return _json(start_response, HTTPStatus.OK, {"users": list_users()})

    if path == "/api/users" and method == "POST":
        if not user:
            return _json(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Autenticação necessária."})
        if not _is_admin(user):
            return _json(start_response, HTTPStatus.FORBIDDEN, {"error": "Acesso exclusivo do Administrador."})
        try:
            payload = _json_body(environ)
            created = create_user(str(payload.get("name", "")), str(payload.get("password", "")))
            return _json(start_response, HTTPStatus.CREATED, {"user": created})
        except ValueError as exc:
            return _json(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    if path.startswith("/api/users/"):
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "users":
            if not user:
                return _json(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Autenticação necessária."})
            if not _is_admin(user):
                return _json(start_response, HTTPStatus.FORBIDDEN, {"error": "Acesso exclusivo do Administrador."})
            try:
                user_id = int(parts[2])
                if len(parts) == 3 and method == "DELETE":
                    delete_user(user_id, user["id"])
                    return _json(start_response, HTTPStatus.OK, {"ok": True})
                if len(parts) == 4 and parts[3] == "password" and method == "PUT":
                    payload = _json_body(environ)
                    reset_user_password(user_id, str(payload.get("password", "")), user["id"])
                    return _json(start_response, HTTPStatus.OK, {"ok": True})
                if len(parts) == 4 and parts[3] == "active" and method == "PUT":
                    payload = _json_body(environ)
                    if not isinstance(payload.get("is_active"), bool):
                        raise ValueError("Situação do usuário inválida.")
                    updated = set_user_active(user_id, payload["is_active"], user["id"])
                    return _json(start_response, HTTPStatus.OK, {"ok": True, "user": updated})
            except (ValueError, TypeError) as exc:
                return _json(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    if path == "/api/units" and method == "GET":
        if not user:
            return _json(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Autenticação necessária."})
        return _json(start_response, HTTPStatus.OK, list_units_payload())

    if path == "/api/units/sync" and method == "POST":
        if not user:
            return _json(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Autenticação necessária."})
        try:
            payload = _json_body(environ)
            units = payload.get("units")
            if not isinstance(units, list):
                raise ValueError("Lista de unidades inválida.")
            result = initialize_units(units, user["id"])
            create_backup(force=True)
            return _json(start_response, HTTPStatus.OK, {"ok": True, **result})
        except ValueError as exc:
            return _json(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    if path.startswith("/api/units/") and method == "PUT":
        if not user:
            return _json(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Autenticação necessária."})
        code = path.rsplit("/", 1)[-1].strip().upper()
        try:
            payload = _json_body(environ)
            unit = payload.get("unit")
            position = int(payload.get("position", 0))
            expected_version_raw = payload.get("expected_version")
            expected_version = int(expected_version_raw) if expected_version_raw is not None else None
            if not isinstance(unit, dict) or str(unit.get("code", "")).upper() != code:
                raise ValueError("Unidade inválida.")
            create_backup()
            result = save_unit(unit, position, user["id"], expected_version)
            return _json(start_response, HTTPStatus.OK, {"ok": True, **result})
        except UnitConflictError as exc:
            return _json(
                start_response,
                HTTPStatus.CONFLICT,
                {"error": str(exc), "conflict": True, "current": exc.current},
            )
        except (ValueError, TypeError) as exc:
            return _json(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    if path == "/api/history" and method == "GET":
        if not user:
            return _json(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Autenticação necessária."})
        try:
            limit = int((query.get("limit") or [100])[0])
        except ValueError:
            limit = 100
        unit_code = (query.get("unit") or [None])[0]
        return _json(start_response, HTTPStatus.OK, {"history": list_history(limit, unit_code)})

    if path == "/api/backup" and method == "POST":
        if not user:
            return _json(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Autenticação necessária."})
        if not _is_admin(user):
            return _json(start_response, HTTPStatus.FORBIDDEN, {"error": "Acesso exclusivo do Administrador."})
        backup = create_backup(force=True)
        return _json(start_response, HTTPStatus.OK, {"ok": True, "backup": backup.name if backup else None})

    if path == "/" and method == "GET":
        if not user:
            return _redirect(start_response, "/login")
        return _file(start_response, BASE_DIR / "index.html")

    parts = [part for part in path.split("/") if part]
    if method == "GET" and parts and parts[0] in STATIC_ROOTS:
        candidate = (BASE_DIR / Path(*parts)).resolve()
        root = (BASE_DIR / parts[0]).resolve()
        if root == candidate or root in candidate.parents:
            return _file(start_response, candidate)

    return _respond(start_response, HTTPStatus.NOT_FOUND, "Rota não encontrada.".encode("utf-8"))


init_db()
create_backup()
