# src/db/init_db.py
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
import sqlite3

from .db_models import Base

DATABASE_URL = "sqlite:///data/axisad.db"

engine = create_engine(DATABASE_URL, echo=True, future=True)

# Enable SQLite foreign key enforcement
@event.listens_for(Engine, "connect")
def enable_sqlite_fk(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

Base.metadata.create_all(engine)

print("DB initialized.")