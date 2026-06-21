"""Stripe key probe — answers "is this key really test or live?".

The key prefix (sk_test_ / sk_live_) is what it *claims*; the API's `livemode`
flag is the ground truth. Comparing the two catches a test key sitting in a prod
config. Read-only: a single GET to /v1/balance.
"""

from __future__ import annotations

from api.services.masking import mask_value

from .evidence import Evidence

STRIPE_BALANCE_URL = "https://api.stripe.com/v1/balance"
_PREFIXES = ("sk_live_", "sk_test_", "rk_live_", "rk_test_")


def _default_get(url: str, api_key: str):
    import httpx

    # Stripe takes the secret key as the basic-auth username.
    resp = httpx.get(url, auth=(api_key, ""), timeout=10)
    ctype = resp.headers.get("content-type", "")
    body = resp.json() if "application/json" in ctype else {}
    return resp.status_code, body, dict(resp.headers)


def probe_stripe_key(api_key: str, *, http_get=None) -> Evidence:
    masked = mask_value("STRIPE_SECRET_KEY", api_key).masked
    prefix = next((p for p in _PREFIXES if api_key.startswith(p)), "")
    claimed = "live" if "live" in prefix else ("test" if "test" in prefix else None)
    observed = {"prefix": prefix.rstrip("_") or None, "claimed_mode": claimed}

    get = http_get or _default_get
    try:
        status, body, _headers = get(STRIPE_BALANCE_URL, api_key)
    except Exception as exc:  # noqa: BLE001
        return Evidence("stripe_key", False, False, observed,
                        "request to Stripe failed", masked, str(exc))

    if status == 401:
        return Evidence("stripe_key", False, False, observed,
                        "Stripe rejected the key (401)", masked, "authentication failed")
    if status != 200:
        return Evidence("stripe_key", False, True, observed,
                        f"unexpected Stripe status {status}", masked, str(body)[:200])

    livemode = bool(body.get("livemode"))
    observed["livemode"] = livemode
    observed["actual_mode"] = "live" if livemode else "test"
    return Evidence(
        probe="stripe_key",
        ok=True,
        reachable=True,
        observed=observed,
        summary=f"Stripe key authenticated; livemode={livemode}",
        masked_input=masked,
    )
