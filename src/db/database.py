# src/db/database.py
from __future__ import annotations

import os
import sqlite3
import sqlcipher3
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

# Put the DB in /data at the project root 
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DB_PATH = os.path.join(_PROJECT_ROOT, "data", "axisad.db")
DATABASE_URL = f"sqlite:///{DEFAULT_DB_PATH}"
DB_KEY = os.environ.get("AX_DB_KEY", "dev-key-change-in-prod")

# Intercept alchemy connection to plain sqlite with sqlcipher 
def _make_connection():
    conn = sqlcipher3.connect(DEFAULT_DB_PATH)
    conn.execute(f"PRAGMA key='{DB_KEY}';")
    return conn

engine = create_engine("sqlite+pysqlite://", creator=_make_connection, echo=False, future=True)

# Enforce foreign keys
@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlcipher3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_session():
    """Context-managed session generator."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()