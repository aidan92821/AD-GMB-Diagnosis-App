# src/db/init_db.py
import os
from src.db.database import engine
from src.db.db_models import Base

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

Base.metadata.create_all(engine)
print("DB initialized.")