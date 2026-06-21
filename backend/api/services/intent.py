"""Intent inference (Phase 2).

For each config key we build a small, bounded slice of *how it is used* in the
codebase and ask Qwen what the value is supposed to be — strictly grounded in
that usage. The result is persisted as an `Intent` row per key.

Grounding is the whole point: the model must reason from the provided code, not
guess from the key's name alone. When there is no usage to ground on, confidence
is capped low so a later probe never "confirms" a fabricated expectation.
"""

from __future__ import annotations

from django.db import transaction

from ..models import AuditEntry, ConfigKey, Intent, Run
from .qwen_client import QwenClient, get_client

_MAX_SLICES = 6          # cap usage snippets per key to keep the prompt bounded
_UNGROUNDED_CONFIDENCE = 0.25  # ceiling when there is no real usage

INTENT_SYSTEM = (
    "You are ActiveEnv's intent-inference engine. Given a single configuration "
    "key and the exact code locations where it is used, infer what the value is "
    "SUPPOSED to be in the target environment.\n\n"
    "Hard rules:\n"
    "1. Ground every conclusion in the provided code usage. Do NOT invent usage "
    "that isn't shown.\n"
    "2. If the usage does not justify a conclusion, say so and lower confidence.\n"
    "3. Never output or guess the secret value itself.\n"
    "4. Reply with a SINGLE JSON object, no prose, exactly these fields:\n"
    '   {"expected_environment": "production|staging|development|any",\n'
    '    "expected_properties": { ... small map, e.g. {"stripe_mode":"live"} },\n'
    '    "gates": "short phrase: what this value controls",\n'
    '    "rationale": "one sentence grounded in the shown usage",\n'
    '    "confidence": 0.0 to 1.0 }'
)


def build_usage_slice(key: ConfigKey) -> tuple[str, int]:
    """Render a bounded text slice of a key's usage sites. Returns (text, count)."""
    sites = list(key.usage_sites.all()[:_MAX_SLICES])
    if not sites:
        return "(no usage of this key was found in the provided codebase)", 0
    blocks = []
    for s in sites:
        blocks.append(
            f"# {s.file_path}:{s.line_number} ({s.usage_kind})\n{s.snippet}"
        )
    return "\n\n".join(blocks), len(sites)


def _build_user_prompt(key: ConfigKey, target_env: str, usage_text: str) -> str:
    return (
        f"Target environment (what the user believes this config is for): {target_env}\n"
        f"Key name: {key.name}\n"
        f"Detected kind: {key.kind}\n"
        f"Masked value: {key.masked_value}\n"
        f"Value hint (non-secret): {key.value_hint}\n\n"
        f"Code usage:\n{usage_text}"
    )


def infer_intent(key: ConfigKey, target_env: str, client: QwenClient) -> Intent:
    """Infer and persist the intent for one key."""
    usage_text, n_sites = build_usage_slice(key)
    grounded = n_sites > 0
    user = _build_user_prompt(key, target_env, usage_text)
    data, raw = client.complete_json(INTENT_SYSTEM, user)

    confidence = float(data.get("confidence", 0.0) or 0.0)
    confidence = max(0.0, min(1.0, confidence))
    if not grounded:
        confidence = min(confidence, _UNGROUNDED_CONFIDENCE)

    intent, _ = Intent.objects.update_or_create(
        config_key=key,
        defaults={
            "expected_environment": str(data.get("expected_environment", "any"))[:32],
            "expected_properties": data.get("expected_properties") or {},
            "gates": str(data.get("gates", ""))[:255],
            "rationale": str(data.get("rationale", "")),
            "confidence": confidence,
            "grounded": grounded,
            "model": getattr(client, "model", ""),
            "raw_response": raw,
        },
    )
    return intent


@transaction.atomic
def infer_run_intents(run: Run, client: QwenClient | None = None) -> Run:
    """Infer intent for every key on a run."""
    client = client or get_client()
    count = 0
    for key in run.keys.all():
        infer_intent(key, run.target_environment, client)
        count += 1

    run.status = Run.Status.INFERRED
    run.save(update_fields=["status", "updated_at"])
    AuditEntry.objects.create(
        run=run,
        action="infer_intent",
        detail={"keys": count, "model": getattr(client, "model", "")},
    )
    return run
