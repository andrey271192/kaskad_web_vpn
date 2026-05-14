"""Пароль веб-интерфейса: переменная окружения или файл после первого входа."""
from __future__ import annotations

import json
import os
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

AUTH_JSON = Path(os.environ.get("WEB_AUTH_JSON", "/var/lib/kaskad/web_auth.json"))
DEFAULT_USER = os.environ.get("BASIC_AUTH_USER", "user1").strip() or "user1"


def ensure_auth_dir() -> None:
    AUTH_JSON.parent.mkdir(parents=True, exist_ok=True)


def auth_from_env() -> bool:
    return bool(os.environ.get("BASIC_AUTH_PASSWORD", "").strip())


def load_record() -> dict | None:
    if not AUTH_JSON.is_file():
        return None
    try:
        raw = json.loads(AUTH_JSON.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def password_is_configured() -> bool:
    if auth_from_env():
        return True
    rec = load_record()
    return bool(rec and rec.get("password_hash"))


def verify_credentials(username: str, password: str) -> bool:
    if auth_from_env():
        u = os.environ.get("BASIC_AUTH_USER", "user1").strip() or "user1"
        epw = os.environ.get("BASIC_AUTH_PASSWORD", "").strip()
        return username == u and password == epw

    rec = load_record()
    if not rec or not rec.get("password_hash"):
        return False
    u = str(rec.get("user") or DEFAULT_USER)
    return username == u and check_password_hash(str(rec["password_hash"]), password)


def save_password(username: str, plaintext: str) -> None:
    ensure_auth_dir()
    h = generate_password_hash(plaintext)
    tmp = AUTH_JSON.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"user": username.strip() or DEFAULT_USER, "password_hash": h}, indent=2),
        encoding="utf-8",
    )
    tmp.replace(AUTH_JSON)
