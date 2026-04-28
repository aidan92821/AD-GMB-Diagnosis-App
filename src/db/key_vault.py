# src/db/key_vault.py
import json
import os
import secrets
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_VAULT_PATH   = os.path.join(_PROJECT_ROOT, "data", "key_vault.json")

# ==== Helper Functions ====
def _load_vault() -> dict:
    if not os.path.exists(_VAULT_PATH):
        return{}
    with open(_VAULT_PATH) as fh:
        return json.load(fh)
    
def _save_vault(vault: dict) -> None:
    os.makedirs(os.path.dirname(_VAULT_PATH), exist_ok=True)
    with open(_VAULT_PATH, "w") as fh:
        json.dump(vault, fh, indent=2)
# ==========================

def user_exists(username: str) -> bool:
    return username in _load_vault()

def create_entry(username: str, password: str, master_key: bytes | None = None) -> bytes:
    vault = _load_vault()
    if username in vault:
        raise ValueError(f"User {username!r} already has a vault entry.")
    
    if master_key is None:
        master_key = secrets.token_bytes(32)

    salt = secrets.token_bytes(16)
    wrapping_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
    nonce = secrets.token_bytes(12)
    aes = AESGCM(wrapping_key)
    ciphertext = aes.encrypt(nonce, master_key, None)

    vault[username] = {
        "pbkdf2_salt": salt.hex(),
        "aes_nonce":   nonce.hex(),
        "ciphertext":  ciphertext.hex(),
    }
    _save_vault(vault)
    return master_key



def unlock(username: str, password: str) -> bytes:
    vault = _load_vault()
    if username not in vault:
        raise ValueError("Invalid username or password.")
    
    entry  = vault[username]
    salt   = bytes.fromhex(entry["pbkdf2_salt"])
    nonce  = bytes.fromhex(entry["aes_nonce"])
    cipher = bytes.fromhex(entry["ciphertext"])
    
    wrapping_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
    aes = AESGCM(wrapping_key)
    try:
        return aes.decrypt(nonce, cipher, None)
    except Exception:
        raise ValueError("Invalid username or password.")
