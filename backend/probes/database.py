"""Database probe — answers "which database did this URL actually hit?".

Strongest leg of the product: `SELECT current_database(), inet_server_addr(),
version()` genuinely reveals the real database and host behind a URL, directly
catching a staging DB used in a prod config. Strictly read-only — the connection
is put into read-only mode and only a single SELECT is ever issued.
"""

from __future__ import annotations

from urllib.parse import urlparse

from api.services.masking import mask_value

from .evidence import Evidence

_CONNECT_TIMEOUT = 5
_PROBE_SQL = "SELECT current_database(), inet_server_addr(), version()"


def probe_database(database_url: str, *, connect=None) -> Evidence:
    """Connect read-only and report the real database identity.

    `connect` is injectable (defaults to psycopg.connect) so tests never need a
    live database.
    """
    masked = mask_value("DATABASE_URL", database_url).masked
    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()

    if not scheme.startswith(("postgres", "postgresql")):
        return Evidence(
            probe="database",
            ok=False,
            reachable=False,
            observed={"scheme": scheme},
            summary="unsupported database scheme",
            masked_input=masked,
            error=f"only postgres is supported in v1, got '{scheme}'",
        )

    observed = {"connect_host": parsed.hostname, "connect_port": parsed.port}

    if connect is None:
        import psycopg  # imported lazily so tests with a fake `connect` need no driver

        connect = psycopg.connect

    try:
        conn = connect(database_url, connect_timeout=_CONNECT_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 — any driver error means unreachable
        return Evidence(
            probe="database",
            ok=False,
            reachable=False,
            observed=observed,
            summary="could not connect to database",
            masked_input=masked,
            error=str(exc),
        )

    try:
        # Belt-and-braces read-only: refuse writes at the protocol level.
        try:
            conn.read_only = True
        except Exception:  # noqa: BLE001 — fake/older drivers may not support it
            pass

        cur = conn.cursor()
        cur.execute(_PROBE_SQL)
        row = cur.fetchone()
        server_addr = row[1]
        observed.update(
            {
                "current_database": row[0],
                "server_addr": str(server_addr) if server_addr is not None else None,
                "version": row[2],
            }
        )
        summary = (
            f"connected to database '{row[0]}' via host '{parsed.hostname}'"
        )
        return Evidence(
            probe="database",
            ok=True,
            reachable=True,
            observed=observed,
            summary=summary,
            masked_input=masked,
        )
    except Exception as exc:  # noqa: BLE001
        return Evidence(
            probe="database",
            ok=False,
            reachable=True,
            observed=observed,
            summary="connected but probe query failed",
            masked_input=masked,
            error=str(exc),
        )
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
