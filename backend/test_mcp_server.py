"""Phase 3: verify the config-probe-mcp server exposes exactly the 3 tools and
routes them to the probe library."""

import asyncio
import pathlib
import sys

_MCP_DIR = pathlib.Path(__file__).resolve().parent.parent / "mcp_server"
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

import server  # noqa: E402


def test_three_probe_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"probe_database", "probe_stripe_key", "probe_github_token"}


def test_database_tool_routes_to_probe_without_network():
    # A non-postgres scheme returns 'unsupported' before any connection attempt.
    out = server.probe_database("redis://localhost:6379/0")
    assert out["probe"] == "database"
    assert out["ok"] is False
