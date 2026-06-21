"""config-probe-mcp — ActiveEnv's MCP server.

Exposes the three read-only probe tools to any MCP client (and, in Phase 4, to
the Qwen agent loop in the Django orchestrator). The server is a thin wrapper:
all real logic lives in the `probes` library so it stays testable and reusable.

Run (stdio):
    python mcp_server/server.py
"""

from __future__ import annotations

import pathlib
import sys

# The probe library lives in the Django backend; make it importable.
_BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from probes import (  # noqa: E402
    probe_database as _probe_database,
    probe_github_token as _probe_github_token,
    probe_stripe_key as _probe_stripe_key,
)

mcp = FastMCP("config-probe-mcp")


@mcp.tool()
def probe_database(database_url: str) -> dict:
    """Connect READ-ONLY to a Postgres URL and report which database actually
    answered (current_database, server address, version). Catches a staging DB
    used in a production config. Never writes."""
    return _probe_database(database_url).to_dict()


@mcp.tool()
def probe_stripe_key(api_key: str) -> dict:
    """Authenticate a Stripe secret key (READ-ONLY GET /v1/balance) and report
    whether it is really test or live via the livemode flag. Catches a test key
    in a production config. Never writes."""
    return _probe_stripe_key(api_key).to_dict()


@mcp.tool()
def probe_github_token(token: str) -> dict:
    """Authenticate a GitHub token (READ-ONLY GET /user) and report the identity
    and scopes behind it. Catches a token for the wrong account/org/scope.
    Never writes."""
    return _probe_github_token(token).to_dict()


if __name__ == "__main__":
    mcp.run()
