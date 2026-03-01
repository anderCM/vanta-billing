import hashlib
import secrets
import uuid

from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_string(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_string(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def encrypt_bytes(data: bytes) -> bytes:
    return _get_fernet().encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    return _get_fernet().decrypt(data)


def generate_client_id() -> str:
    return str(uuid.uuid4())


def generate_api_key() -> str:
    return f"sk_live_{secrets.token_urlsafe(48)}"


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(key: str, key_hash: str) -> bool:
    return hash_api_key(key) == key_hash
