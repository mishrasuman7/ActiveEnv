"""Simulated probes for offline demos and development.

These derive evidence from the *self-describing* parts of a credential without
touching the network: a Stripe key's sk_test_/sk_live_ prefix is ground truth
for its mode, and a database URL's host/name is exactly what it would connect
to. This lets the full reveal run with no Docker, Stripe, or GitHub creds —
and serves as a reliable demo fallback. Toggle with SIMULATE_PROBES.
"""

from __future__ import annotations

from urllib.parse import urlparse

from api.services.masking import mask_value

from .evidence import Evidence


def simulate_database(database_url: str) -> Evidence:
    p = urlparse(database_url)
    dbname = (p.path or "/").lstrip("/") or "unknown"
    observed = {
        "connect_host": p.hostname,
        "connect_port": p.port,
        "current_database": dbname,
        "server_addr": "(simulated)",
        "version": "PostgreSQL 16 (simulated)",
    }
    return Evidence(
        probe="database",
        ok=True,
        reachable=True,
        observed=observed,
        summary=f"connected to database '{dbname}' via host '{p.hostname}' (simulated)",
        masked_input=mask_value("DATABASE_URL", database_url).masked,
    )


def simulate_stripe(api_key: str) -> Evidence:
    live = api_key.startswith(("sk_live_", "rk_live_"))
    test = api_key.startswith(("sk_test_", "rk_test_"))
    mode = "live" if live else ("test" if test else None)
    observed = {
        "prefix": ("sk_live" if live else "sk_test" if test else None),
        "claimed_mode": mode,
        "livemode": live,
        "actual_mode": mode,
    }
    return Evidence(
        probe="stripe_key",
        ok=True,
        reachable=True,
        observed=observed,
        summary=f"Stripe key authenticated; livemode={live} (simulated)",
        masked_input=mask_value("STRIPE_SECRET_KEY", api_key).masked,
    )


def simulate_github(token: str) -> Evidence:
    observed = {
        "login": "demo-user",
        "account_id": 1,
        "account_type": "User",
        "scopes": ["repo", "read:org"],
    }
    return Evidence(
        probe="github_token",
        ok=True,
        reachable=True,
        observed=observed,
        summary="token belongs to 'demo-user' with scopes ['repo', 'read:org'] (simulated)",
        masked_input=mask_value("GITHUB_TOKEN", token).masked,
    )
