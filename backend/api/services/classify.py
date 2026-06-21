"""Classification (intent vs. reality).

Compares what a key is supposed to be (Intent, Phase 2) against what it actually
is (Evidence, Phase 3) and returns a verdict with evidence and blast radius.

Verdicts are deterministic on purpose — the demo's reveal must be reliable, not
a coin flip. The signals that drive a "silently wrong" verdict come from observed
reality (a DB's real host, Stripe's livemode flag), so they hold even when intent
is weak. When a verdict would rely on low-confidence intent, it is softened to
"suspect" rather than asserted.
"""

from __future__ import annotations

from probes import Evidence

# Tokens in a DB host/name that mean "not production".
_NON_PROD_TOKENS = (
    "staging", "stage", "dev", "development", "test", "qa",
    "sandbox", "local", "uat", "preview",
)

CORRECT = "correct"
SUSPECT = "suspect"
SILENTLY_WRONG = "silently_wrong"


def _result(classification, expected, evidence, blast="", fix="", confidence=0.0):
    return {
        "classification": classification,
        "expected": expected,
        "evidence": evidence.summary if isinstance(evidence, Evidence) else "",
        "reality": evidence.observed if isinstance(evidence, Evidence) else {},
        "blast_radius": blast,
        "proposed_fix": fix,
        "confidence": round(confidence, 2),
    }


def classify(key, intent, evidence: Evidence, target_env: str) -> dict:
    """Return a finding dict for one probed key."""
    # Couldn't observe reality → we can't assert anything. Suspect, not wrong.
    if not evidence.reachable or not evidence.ok:
        return {
            "classification": SUSPECT,
            "expected": _expected_from_intent(intent, target_env, key.kind),
            "evidence": evidence.summary or "probe could not verify reality",
            "reality": {"error": evidence.error, **evidence.observed},
            "blast_radius": "Could not verify — the value may still be wrong.",
            "proposed_fix": "",
            "confidence": 0.2,
        }

    if key.kind == "stripe_key":
        return _classify_stripe(intent, evidence, target_env)
    if key.kind == "database_url":
        return _classify_database(intent, evidence, target_env)
    if key.kind == "github_token":
        return _classify_github(intent, evidence, target_env)

    return _result(SUSPECT, {}, evidence, confidence=0.2)


def _expected_from_intent(intent, target_env, kind):
    if intent is not None:
        return {
            "environment": intent.expected_environment,
            **(intent.expected_properties or {}),
        }
    return {"environment": target_env}


# --- per-adapter ---------------------------------------------------------

def _classify_stripe(intent, evidence, target_env):
    props = (intent.expected_properties if intent else {}) or {}
    # Expectation: explicit intent property, else prod => live.
    expected_mode = props.get("stripe_mode")
    from_intent = expected_mode is not None
    if not expected_mode and target_env == "production":
        expected_mode = "live"
    actual_mode = evidence.observed.get("actual_mode")
    expected = {"environment": target_env, "stripe_mode": expected_mode}

    if expected_mode and actual_mode and actual_mode != expected_mode:
        confidence = (intent.confidence if (from_intent and intent) else 0.9)
        classification = SILENTLY_WRONG if confidence >= 0.4 else SUSPECT
        blast = (
            "Payments run in the wrong mode: a test key in production silently "
            "fails to charge customers (lost revenue); a live key in test moves "
            "real money."
        )
        fix = f"replace with a {expected_mode}-mode key (sk_{expected_mode}_...)"
        return _result(classification, expected, evidence, blast, fix, confidence)

    if expected_mode and actual_mode == expected_mode:
        return _result(CORRECT, expected, evidence, confidence=0.9)
    return _result(SUSPECT, expected, evidence, confidence=0.3)


def _classify_database(intent, evidence, target_env):
    host = (evidence.observed.get("connect_host") or "").lower()
    dbname = (evidence.observed.get("current_database") or "").lower()
    expected_env = intent.expected_environment if intent else target_env
    expected = {"environment": expected_env}
    signals = sorted({t for t in _NON_PROD_TOKENS if t in host or t in dbname})

    if (expected_env or target_env) == "production" and signals:
        blast = (
            "The app believes it is in production but is connected to a "
            "non-production database — risk of corrupting or serving the wrong "
            "data."
        )
        fix = "point DATABASE_URL at the production database"
        return _result(SILENTLY_WRONG, expected, evidence, blast, fix, 0.9)

    return _result(CORRECT, expected, evidence, confidence=0.8)


def _classify_github(intent, evidence, target_env):
    props = (intent.expected_properties if intent else {}) or {}
    expected_login = props.get("expected_login") or props.get("login")
    expected_org = props.get("expected_org") or props.get("org")
    login = evidence.observed.get("login")
    expected = {"environment": target_env, "login": expected_login, "org": expected_org}

    if expected_login and login and expected_login != login:
        confidence = intent.confidence if intent else 0.5
        classification = SILENTLY_WRONG if confidence >= 0.4 else SUSPECT
        blast = (
            "Token authenticates as the wrong GitHub account — CI and API calls "
            "act under an unintended identity and permissions."
        )
        fix = f"use a token for account '{expected_login}'"
        return _result(classification, expected, evidence, blast, fix, confidence)

    return _result(CORRECT, expected, evidence, confidence=0.7)
