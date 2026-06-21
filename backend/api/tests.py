"""Phase 1 tests: masking, parsing, usage location, and the ingestion API."""

import json

import pytest

from api.services.config_parser import parse_config
from api.services.masking import detect_kind, mask_value
from api.services.usage_locator import locate_usages


# --- masking -------------------------------------------------------------

def test_stripe_kind_and_prefix_preserved():
    r = mask_value("STRIPE_SECRET_KEY", "sk_live_51AbCdEfGh1234")
    assert r.kind == "stripe_key"
    assert r.is_probeable and r.is_secret
    assert r.hint == "sk_live"           # the test/live signal is kept
    assert "51AbCdEfGh" not in r.masked  # body never leaks


def test_database_url_masks_only_password():
    r = mask_value("DATABASE_URL", "postgres://admin:secret@staging-db:5432/app")
    assert r.kind == "database_url"
    assert "secret" not in r.masked
    assert "staging-db" in r.masked      # host kept — it's the staging-in-prod signal


def test_non_secret_value_not_masked():
    r = mask_value("DJANGO_DEBUG", "true")
    assert r.kind == "unknown"
    assert not r.is_secret
    assert r.masked == "true"


def test_github_token_detected_by_prefix():
    assert detect_kind("SOME_PAT", "ghp_abc123") == "github_token"


# --- parser --------------------------------------------------------------

def test_env_parsing_strips_comments_and_quotes():
    fmt, keys = parse_config('FOO="bar"  # note\nBAZ=qux # c\n')
    assert fmt == "env"
    d = {k.name: k.value for k in keys}
    assert d == {"FOO": "bar", "BAZ": "qux"}


def test_python_settings_parsed_via_ast():
    fmt, keys = parse_config("import os\nDEBUG = True\nNAME = 'x'\n")
    assert fmt == "python"
    assert {k.name for k in keys} == {"DEBUG", "NAME"}


def test_json_nested_flattened():
    fmt, keys = parse_config('{"A": "1", "n": {"B": "2"}}')
    assert fmt == "json"
    assert {k.name for k in keys} == {"A", "n_B"}


# --- usage locator -------------------------------------------------------

def test_locator_finds_env_and_settings_usage():
    files = {
        "billing.py": "def f():\n    return os.environ['STRIPE_SECRET_KEY']\n",
        "db.py": "def g():\n    return settings.DATABASE_URL\n",
    }
    hits = locate_usages(files, ["STRIPE_SECRET_KEY", "DATABASE_URL"])
    assert len(hits["STRIPE_SECRET_KEY"]) == 1
    assert len(hits["DATABASE_URL"]) == 1
    assert hits["STRIPE_SECRET_KEY"][0].usage_kind == "os.environ"


def test_locator_ignores_longer_identifiers():
    files = {"a.py": 'OLD_DATABASE_URL = 1\nMY_DATABASE_URL_X = 2\n'}
    hits = locate_usages(files, ["DATABASE_URL"])
    assert hits["DATABASE_URL"] == []


# --- ingestion API -------------------------------------------------------

@pytest.mark.django_db
def test_ingest_run_creates_masked_inventory_with_usages(client):
    payload = {
        "target_environment": "production",
        "config_text": (
            "DATABASE_URL=postgres://admin:secret@staging-db:5432/app\n"
            "STRIPE_SECRET_KEY=sk_test_51AbCdEf\n"
        ),
        "files": {
            "billing.py": "def charge():\n    return os.environ['STRIPE_SECRET_KEY']\n",
            "db.py": "def conn():\n    return settings.DATABASE_URL\n",
        },
    }
    resp = client.post(
        "/api/runs/", data=json.dumps(payload), content_type="application/json"
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "parsed"
    assert data["config_format"] == "env"
    assert data["key_count"] == 2

    by_name = {k["name"]: k for k in data["keys"]}
    assert by_name["STRIPE_SECRET_KEY"]["kind"] == "stripe_key"
    assert by_name["STRIPE_SECRET_KEY"]["is_probeable"] is True
    assert by_name["STRIPE_SECRET_KEY"]["usage_count"] == 1
    # secret never echoed back in plaintext
    assert "sk_test_51AbCdEf" not in resp.content.decode()
    assert "secret@" not in resp.content.decode()
