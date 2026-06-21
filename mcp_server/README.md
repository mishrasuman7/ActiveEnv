# config-probe-mcp

ActiveEnv's custom **MCP server**, exposing three **strictly read-only** probe tools.
The Qwen agent loop (in the Django backend) calls these tools to observe what a
config value *actually* points at — the "reality" half of the product.

## Tools

| Tool | What it does | Read-only guarantee |
|---|---|---|
| `probe_database` | Connects to a Postgres URL, runs `SELECT current_database(), inet_server_addr(), version()` | Connection forced read-only; only a SELECT is issued |
| `probe_stripe_key` | `GET /v1/balance`, reads the `livemode` flag vs. the key's `sk_test_`/`sk_live_` prefix | Single GET; no writes |
| `probe_github_token` | `GET /user` + `X-OAuth-Scopes` header for identity & scope | Single GET; no writes |

Every tool returns a normalized `Evidence` object with all secrets masked.

## Run

```bash
pip install -r requirements.txt
python server.py        # serves over stdio
```

The real probe logic lives in [`../backend/probes`](../backend/probes) so it is
shared with the Django orchestrator and unit-tested without live credentials.
