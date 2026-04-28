import sys
sys.path.insert(0, 'src')
from db.key_vault import unlock
import sqlcipher3

username = input("Username: ")
password = input("Password: ")

master_key = unlock(username, password)
conn = sqlcipher3.connect('data/axisad.db')
conn.execute(f"PRAGMA key=\"x'{master_key.hex()}'\"")

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
