"""Phase 3 tests: the three read-only probes, exercised with fakes.

No live database or network is touched — `connect`/`http_get` are injected.
These also assert the read-only guarantee (DB connection forced read-only,
only a SELECT issued).
"""

from probes import probe_database, probe_github_token, probe_stripe_key


# --- database ------------------------------------------------------------

class _FakeCursor:
    def __init__(self, row):
        self.row = row
        self.executed = []

    def execute(self, sql, *args):
        self.executed.append(sql)

    def fetchone(self):
        return self.row


class _FakeConn:
    def __init__(self, row):
        self.row = row
        self.read_only = None
        self.closed = False
        self.cur = None

    def cursor(self):
        self.cur = _FakeCursor(self.row)
        return self.cur

    def close(self):
        self.closed = True


def test_database_probe_reports_real_identity_and_is_read_only():
    holder = {}

    def connect(url, **kwargs):
        conn = _FakeConn(("app_prod", "10.0.0.5", "PostgreSQL 16.1"))
        holder["conn"] = conn
        return conn

    ev = probe_database(
        "postgres://admin:secret@staging-db:5432/app", connect=connect
    )

    assert ev.ok and ev.reachable
    assert ev.observed["current_database"] == "app_prod"
    assert ev.observed["connect_host"] == "staging-db"
    assert ev.observed["version"].startswith("PostgreSQL")
    # read-only enforced + only a SELECT was ever issued
    assert holder["conn"].read_only is True
    assert holder["conn"].cur.executed and all(
        s.strip().upper().startswith("SELECT") for s in holder["conn"].cur.executed
    )
    assert holder["conn"].closed is True
    # password never leaks
    assert "secret" not in ev.masked_input


def test_database_probe_unreachable_is_handled():
    def connect(url, **kwargs):
        raise OSError("connection refused")

    ev = probe_database("postgres://u:p@nope:5432/db", connect=connect)
    assert ev.ok is False and ev.reachable is False
    assert "connection refused" in ev.error


def test_database_probe_rejects_non_postgres():
    ev = probe_database("redis://localhost:6379/0")
    assert ev.ok is False
    assert "scheme" in ev.observed


# --- stripe --------------------------------------------------------------

def test_stripe_probe_detects_mode_mismatch():
    # Key claims live by prefix, but reality says livemode=false → mismatch.
    def http_get(url, api_key):
        return 200, {"object": "balance", "livemode": False}, {}

    ev = probe_stripe_key("sk_live_51AbCdEfGhIj", http_get=http_get)
    assert ev.ok and ev.reachable
    assert ev.observed["claimed_mode"] == "live"
    assert ev.observed["livemode"] is False
    assert ev.observed["actual_mode"] == "test"
    assert "AbCdEfGhIj" not in ev.masked_input


def test_stripe_probe_401_rejected():
    def http_get(url, api_key):
        return 401, {}, {}

    ev = probe_stripe_key("sk_test_bad", http_get=http_get)
    assert ev.ok is False and ev.reachable is False


# --- github --------------------------------------------------------------

def test_github_probe_reports_identity_and_scopes():
    def http_get(url, token):
        return (
            200,
            {"login": "octocat", "id": 583231, "type": "User"},
            {"X-OAuth-Scopes": "repo, read:org"},
        )

    ev = probe_github_token("ghp_AbCdEfGhIj", http_get=http_get)
    assert ev.ok and ev.reachable
    assert ev.observed["login"] == "octocat"
    assert ev.observed["account_id"] == 583231
    assert ev.observed["scopes"] == ["repo", "read:org"]
    assert "AbCdEfGhIj" not in ev.masked_input


def test_github_probe_401_rejected():
    def http_get(url, token):
        return 401, {}, {}

    ev = probe_github_token("ghp_bad", http_get=http_get)
    assert ev.ok is False and ev.reachable is False
