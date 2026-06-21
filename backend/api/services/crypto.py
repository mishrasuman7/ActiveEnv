"""Symmetric encryption for the secret vault.

Probeable credentials are encrypted with Fernet before they touch the database,
and only ever decrypted transiently inside a probe call. Plaintext secrets are
never persisted, logged, or returned by the API.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet
from django.conf import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(settings.SECRET_VAULT_KEY.encode())


def encrypt(value: str) -> str:
    """Encrypt a secret value to a urlsafe token (empty in → empty out)."""
    if not value:
        return ""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a vault token back to its plaintext value (transient use only)."""
    if not token:
        return ""
    return _fernet().decrypt(token.encode()).decode()
