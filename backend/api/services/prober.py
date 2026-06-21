"""Probe dispatch (the "plan probes → execute probes" step).

Given a probeable ConfigKey, decrypt its vaulted value transiently, route it to
the right read-only probe adapter, and return normalized Evidence. The plaintext
value lives only inside this function call.

The probe callables are injectable so the orchestrator and tests can run without
touching a real database or network.
"""

from __future__ import annotations

from django.conf import settings

from probes import Evidence, probe_database, probe_github_token, probe_stripe_key
from probes.simulate import simulate_database, simulate_github, simulate_stripe

from ..models import ConfigKey
from .crypto import decrypt

# kind -> probe function
_ADAPTERS = {
    "database_url": probe_database,
    "stripe_key": probe_stripe_key,
    "github_token": probe_github_token,
}

# Offline/demo adapters that read self-describing signals without the network.
_SIMULATED = {
    "database_url": simulate_database,
    "stripe_key": simulate_stripe,
    "github_token": simulate_github,
}


def _active_adapters() -> dict:
    if getattr(settings, "SIMULATE_PROBES", False):
        return _SIMULATED
    return _ADAPTERS


def probe_key(key: ConfigKey, adapters: dict | None = None) -> Evidence:
    """Run the correct read-only probe for a key and return its Evidence."""
    adapters = adapters or _active_adapters()
    probe = adapters.get(key.kind)
    if probe is None:
        return Evidence(
            probe=key.kind or "unknown",
            ok=False,
            reachable=False,
            observed={},
            summary="no probe adapter for this key kind",
            masked_input=key.masked_value,
            error=f"unsupported kind '{key.kind}'",
        )

    value = decrypt(key.secret_ciphertext)
    if not value:
        return Evidence(
            probe=key.kind,
            ok=False,
            reachable=False,
            observed={},
            summary="no vaulted value to probe",
            masked_input=key.masked_value,
            error="missing secret_ciphertext",
        )

    return probe(value)
