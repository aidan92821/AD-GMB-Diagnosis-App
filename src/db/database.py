# src/db/database.py
from __future__ import annotations

import os
import sqlite3
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

# Put the DB in /data so it doesn't clutter the repo
DEFAULT_DB_PATH = os.path.join("data", "axisad.db")
DATABASE_URL = f"sqlite:///{DEFAULT_DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False, future=True)

# Enforce foreign keys
@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
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