import sys
import hashlib
import os

sys.path.insert(0, 'src')
import sqlcipher3

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

username = input("Username: ")
password = input("Password: ")

salt_path = os.path.join(_DATA_DIR, f"{username}.salt")
if not os.path.exists(salt_path):
    print(f"No salt file found for user {username!r}. Have they registered?")
    sys.exit(1)

with open(salt_path, "rb") as f:
    salt = f.read()

key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
db_path = os.path.join(_DATA_DIR, f"axisad_{username}.db")

conn = sqlcipher3.connect(db_path)
conn.execute(f"PRAGMA key=\"x'{key.hex()}'\"")

print("\nTables:", [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()])
print()

while True:
    query = input("SQL> ")
    if query.lower() in ("exit", "quit"):
        break
    try:
        rows = conn.execute(query).fetchall()
        for row in rows:
            print(row)
    except Exception as e:
        print("Error:", e)
