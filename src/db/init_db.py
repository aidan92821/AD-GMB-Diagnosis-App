# src/db/init_db.py
from src.db.database import get_engine
from src.db.db_models import Base
import os

def init_db():
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(get_engine())
