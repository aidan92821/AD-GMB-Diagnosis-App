# src/db/init_db.py
import os
from src.db.database import engine
from src.db.db_models import Base


def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(engine)
    print("DB initialized.")