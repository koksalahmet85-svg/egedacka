"""TCKN / IBAN gibi alanlar için uygulama katmanı şifreleme (KVKK md.12 teknik tedbir)."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import get_settings


def _key() -> bytes:
    raw = get_settings().field_encryption_key
    if not raw:
        raise RuntimeError("FIELD_ENCRYPTION_KEY tanımlı değil")
    return base64.b64decode(raw)


def encrypt(plain: str) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, plain.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(token: str) -> str:
    blob = base64.b64decode(token)
    return AESGCM(_key()).decrypt(blob[:12], blob[12:], None).decode()
