# src/db/database.py
from __future__ import annotations

import os
import sqlcipher3
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

# Put the DB in /data at the project root 
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DB_PATH = os.path.join(_PROJECT_ROOT, "data", "axisad.db")
DATABASE_URL = f"sqlite:///{DEFAULT_DB_PATH}"

_engine         = None
_SessionLocal   = None
_master_key     = None 

class _SessionProxy:
    def __call__(self, *args, **kwargs):
        if _SessionLocal is None:
            raise RuntimeError("Database not initialized. Call init_engine() first.")
        return _SessionLocal(*args, **kwargs)

SessionLocal = _SessionProxy()

def init_engine(master_key: bytes) -> None:
    global _engine, _SessionLocal, _master_key
    _master_key = master_key

    hex_key = master_key.hex()

    def _make_connection():
        conn = sqlcipher3.connect(DEFAULT_DB_PATH)
        conn.execute(f"PRAGMA key=\"x'{hex_key}'\";")
        return conn

    _engine = create_engine("sqlite+pysqlite://", creator=_make_connection, echo=False, future=True)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)

def get_engine():
    return _engine

def get_master_key() -> bytes | None:
    return _master_key

# Enforce foreign keys
@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlcipher3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

def get_session():
    """Context-managed session generator."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()