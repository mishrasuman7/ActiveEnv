"""Tests: masking, parsing, usage location, ingestion API, and intent inference."""

import json

import pytest

from api.services.config_parser import parse_config
from api.services.masking import detect_kind, mask_value
from api.services.usage_locator import locate_usages


class FakeQwen:
    """Stand-in for QwenClient so the intent layer is testable without a key."""

    model = "qwen-fake"

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete_json(self, system, user, *, temperature=0.0):
        self.calls.append(user)
        return self.payload, json.dumps(self.payload)


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


# --- intent inference (Phase 2) -----------------------------------------

def _make_run_with_key(usage=True):
    from api.models import ConfigKey, Run, UsageSite

    run = Run.objects.create(target_environment="production")
    key = ConfigKey.objects.create(
        run=run, name="STRIPE_SECRET_KEY", kind="stripe_key",
        masked_value="sk_test_****1234", value_hint="sk_test", is_probeable=True,
    )
    if usage:
        UsageSite.objects.create(
            config_key=key, file_path="billing.py", line_number=2,
            usage_kind="os.environ",
            snippet="def charge():\n    stripe.api_key = os.environ['STRIPE_SECRET_KEY']",
        )
    return run, key


@pytest.mark.django_db
def test_infer_intent_persists_grounded_result():
    from api.services.intent import infer_intent

    _run, key = _make_run_with_key(usage=True)
    fake = FakeQwen({
        "expected_environment": "production",
        "expected_properties": {"stripe_mode": "live"},
        "gates": "charging customers",
        "rationale": "Key is used on the customer charge path, so prod must be live.",
        "confidence": 0.9,
    })
    intent = infer_intent(key, "production", fake)

    assert intent.expected_environment == "production"
    assert intent.expected_properties == {"stripe_mode": "live"}
    assert intent.grounded is True
    assert intent.confidence == 0.9
    assert "charge" in fake.calls[0]  # the usage snippet reached the prompt


@pytest.mark.django_db
def test_ungrounded_intent_confidence_is_capped():
    from api.services.intent import infer_intent

    _run, key = _make_run_with_key(usage=False)
    fake = FakeQwen({"expected_environment": "production", "confidence": 0.95})
    intent = infer_intent(key, "production", fake)

    assert intent.grounded is False
    assert intent.confidence <= 0.25  # cannot be confident without real usage


@pytest.mark.django_db
def test_infer_endpoint_returns_503_without_api_key(client):
    run, _key = _make_run_with_key(usage=True)
    resp = client.post(f"/api/runs/{run.id}/infer/")
    assert resp.status_code == 503  # QwenNotConfigured surfaced cleanly


@pytest.mark.django_db
def test_infer_endpoint_runs_with_injected_client(client, monkeypatch):
    import api.views as views_module

    fake = FakeQwen({
        "expected_environment": "production",
        "expected_properties": {"stripe_mode": "live"},
        "gates": "charging customers",
        "rationale": "Used on the charge path.",
        "confidence": 0.8,
    })
    # Patch the client factory used inside the inference service.
    monkeypatch.setattr("api.services.intent.get_client", lambda: fake)

    run, _key = _make_run_with_key(usage=True)
    resp = client.post(f"/api/runs/{run.id}/infer/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "inferred"
    intent = data["keys"][0]["intent"]
    assert intent["expected_environment"] == "production"
    assert intent["confidence"] == 0.8
