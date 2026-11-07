import hashlib
import secrets
from datetime import datetime, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(24))

def now():
    return datetime.now(timezone.utc).timestamp()

def token():
    return secrets.token_urlsafe(48)

def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()

def hash_password(value: str):
    return hasher.hash(value)

def verify_password(value: str, hashed: str):
    try:
        return hasher.verify(hashed, value)
    except (VerificationError, InvalidHashError):
        return False
