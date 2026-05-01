# src/db/database.py
from __future__ import annotations

import hashlib
import os
import secrets
import sqlcipher3
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR     = os.path.join(_PROJECT_ROOT, "data")

_PBKDF2_ITERS = 600_000

_engine       = None
_SessionLocal = None
_db_path      = None


class _SessionProxy:
    def __call__(self, *args, **kwargs):
        if _SessionLocal is None:
            raise RuntimeError("Database not initialized. Call init_engine() first.")
        return _SessionLocal(*args, **kwargs)


SessionLocal = _SessionProxy()


def get_db_path(username: str) -> str:
    return os.path.join(_DATA_DIR, f"axisad_{username}.db")


def get_salt_path(username: str) -> str:
    return os.path.join(_DATA_DIR, f"{username}.salt")


def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERS)


def init_engine(username: str, password: str) -> None:
    global _engine, _SessionLocal, _db_path

    os.makedirs(_DATA_DIR, exist_ok=True)

    salt_path = get_salt_path(username)
    if os.path.exists(salt_path):
        with open(salt_path, "rb") as f:
            salt = f.read()
    else:
        salt = secrets.token_bytes(16)
        with open(salt_path, "wb") as f:
            f.write(salt)

    key      = _derive_key(password, salt)
    hex_key  = key.hex()
    db_path  = get_db_path(username)
    _db_path = db_path

    def _make_connection():
        conn = sqlcipher3.connect(db_path)
        conn.execute(f"PRAGMA key=\"x'{hex_key}'\";")
        return conn

    _engine = create_engine("sqlite+pysqlite://", creator=_make_connection, echo=False, future=True)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def get_engine():
    return _engine


def get_db_path_active() -> str | None:
    return _db_path


@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlcipher3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
