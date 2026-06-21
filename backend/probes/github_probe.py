"""GitHub token probe — answers "whose token is this, and what can it do?".

`GET /user` reveals the identity behind the token; the `X-OAuth-Scopes` response
header reveals its scopes. Together they catch a token for the wrong account/org
or with the wrong scope. Read-only: a single GET to /user.
"""

from __future__ import annotations

from api.services.masking import mask_value

from .evidence import Evidence

GITHUB_USER_URL = "https://api.github.com/user"


def _default_get(url: str, token: str):
    import httpx

    resp = httpx.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=10,
    )
    body = resp.json() if resp.content else {}
    return resp.status_code, body, dict(resp.headers)


def probe_github_token(token: str, *, http_get=None) -> Evidence:
    masked = mask_value("GITHUB_TOKEN", token).masked
    observed: dict = {}

    get = http_get or _default_get
    try:
        status, body, headers = get(GITHUB_USER_URL, token)
    except Exception as exc:  # noqa: BLE001
        return Evidence("github_token", False, False, observed,
                        "request to GitHub failed", masked, str(exc))

    if status == 401:
        return Evidence("github_token", False, False, observed,
                        "GitHub rejected the token (401)", masked, "authentication failed")
    if status != 200:
        return Evidence("github_token", False, True, observed,
                        f"unexpected GitHub status {status}", masked, str(body)[:200])

    # Header names are case-insensitive; normalize for the lookup.
    lower = {k.lower(): v for k, v in headers.items()}
    scopes_raw = lower.get("x-oauth-scopes", "") or ""
    observed.update(
        {
            "login": body.get("login"),
            "account_id": body.get("id"),
            "account_type": body.get("type"),
            "scopes": [s.strip() for s in scopes_raw.split(",") if s.strip()],
        }
    )
    return Evidence(
        probe="github_token",
        ok=True,
        reachable=True,
        observed=observed,
        summary=f"token belongs to '{body.get('login')}' with scopes {observed['scopes']}",
        masked_input=masked,
    )
