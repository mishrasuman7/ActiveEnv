"""Secret masking + lightweight kind detection.

Safety rule (non-negotiable): a raw secret value never leaves this module.
Callers get a masked string for display plus a tiny non-sensitive `hint`
(prefix / scheme / last-4) that is safe to store and is enough to classify and
plan a probe. The unmasked value is only ever held transiently in memory while a
probe runs — it is never persisted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

# Heuristics for what a key is, from its name and/or value.
_STRIPE_PREFIXES = ("sk_test_", "sk_live_", "pk_test_", "pk_live_", "rk_test_", "rk_live_")
_GITHUB_PREFIXES = ("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_")
_DB_SCHEMES = ("postgres", "postgresql", "mysql", "mariadb", "sqlite")

# Key-name substrings that imply a secret even when the value looks innocuous.
_SECRET_NAME_HINTS = (
    "secret", "token", "key", "password", "passwd", "pwd", "api",
    "auth", "credential", "private", "dsn",
)
# Key-name substrings that are NOT secrets (avoid masking booleans/hosts/ports).
_NONSECRET_NAMES = (
    "debug", "host", "hostname", "port", "name", "env", "environment",
    "region", "timeout", "level",
)


@dataclass
class MaskResult:
    masked: str          # safe-to-display rendering
    hint: str            # tiny non-sensitive classifier hint
    kind: str            # database_url | stripe_key | github_token | unknown
    is_secret: bool
    is_probeable: bool


def detect_kind(name: str, value: str) -> str:
    """Classify a key as one of the three probeable adapters, or unknown."""
    n = name.lower()
    v = (value or "").strip()

    if v.startswith(_STRIPE_PREFIXES) or "stripe" in n:
        return "stripe_key"
    if v.startswith(_GITHUB_PREFIXES) or "github" in n:
        return "github_token"
    scheme = v.split("://", 1)[0].lower() if "://" in v else ""
    if scheme in _DB_SCHEMES or "database_url" in n or n.endswith("_db_url"):
        return "database_url"
    return "unknown"


def _looks_secret(name: str, value: str, kind: str) -> bool:
    if kind in ("stripe_key", "github_token"):
        return True
    if kind == "database_url":
        # The URL itself usually embeds a password.
        return "@" in value
    n = name.lower()
    if any(h and h in n for h in _NONSECRET_NAMES):
        return False
    return any(h in n for h in _SECRET_NAME_HINTS)


def _mask_token(value: str, keep_prefix: str = "", last: int = 4) -> str:
    if not value:
        return ""
    tail = value[-last:] if len(value) > last else ""
    return f"{keep_prefix}{'*' * 8}{tail}"


def _mask_db_url(value: str) -> str:
    """Mask only the password inside a DB URL, keep structure for readability."""
    try:
        p = urlparse(value)
    except ValueError:
        return "********"
    if p.password:
        netloc = p.netloc.replace(f":{p.password}@", ":****@")
        p = p._replace(netloc=netloc)
    return urlunparse(p)


def mask_value(name: str, value: str) -> MaskResult:
    """Mask a single config value and describe it without leaking the secret."""
    value = "" if value is None else str(value)
    kind = detect_kind(name, value)
    is_secret = _looks_secret(name, value, kind)

    if kind == "stripe_key":
        prefix = next((p for p in _STRIPE_PREFIXES if value.startswith(p)), "")
        masked = _mask_token(value, keep_prefix=prefix)
        # The prefix (test vs live) is the whole game for Stripe — keep it as hint.
        hint = prefix.rstrip("_") if prefix else "stripe"
        return MaskResult(masked, hint, kind, True, is_probeable=True)

    if kind == "github_token":
        prefix = next((p for p in _GITHUB_PREFIXES if value.startswith(p)), "")
        masked = _mask_token(value, keep_prefix=prefix)
        hint = prefix.rstrip("_") if prefix else "github"
        return MaskResult(masked, hint, kind, True, is_probeable=True)

    if kind == "database_url":
        masked = _mask_db_url(value)
        scheme = value.split("://", 1)[0].lower() if "://" in value else ""
        host = ""
        try:
            host = urlparse(value).hostname or ""
        except ValueError:
            pass
        hint = f"{scheme}://{host}" if scheme else "db"
        return MaskResult(masked, hint, kind, is_secret, is_probeable=True)

    # Unknown / generic
    if is_secret:
        masked = _mask_token(value)
        hint = f"len{len(value)}"
    else:
        masked = value
        hint = value[:32]
    return MaskResult(masked, hint, kind, is_secret, is_probeable=False)
