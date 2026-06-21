"""Human-in-the-loop fix application + undo (Phase 5).

Nothing here runs without explicit human approval at the API layer. Applying a
fix swaps in the corrected (encrypted) value, snapshots the previous state for
undo, then re-probes the key so the finding flips to green when reality finally
matches intent. Every action is recorded in the audit log and is reversible.
"""

from __future__ import annotations

from django.db import transaction

from ..models import AuditEntry, Finding, Fix
from .crypto import encrypt
from .masking import mask_value
from .orchestrator import probe_and_classify_key


def _snapshot(key) -> dict:
    return {
        "ciphertext": key.secret_ciphertext,
        "masked": key.masked_value,
        "hint": key.value_hint,
        "kind": key.kind,
        "is_probeable": key.is_probeable,
    }


@transaction.atomic
def apply_fix(finding: Finding, corrected_value: str, adapters: dict | None = None) -> Finding:
    """Apply an approved corrected value to a key, then re-probe to confirm."""
    key = finding.config_key
    run = finding.run

    fix = Fix.objects.create(
        run=run,
        finding=finding,
        config_key=key,
        previous_state=_snapshot(key),
        rationale=finding.proposed_fix,
    )

    # Swap in the corrected value (re-masked, re-classified kind, re-vaulted).
    m = mask_value(key.name, corrected_value)
    key.masked_value = m.masked
    key.value_hint = m.hint
    key.kind = m.kind
    key.is_probeable = m.is_probeable
    key.secret_ciphertext = encrypt(corrected_value)
    key.save()

    fix.new_masked = m.masked
    fix.save(update_fields=["new_masked"])

    AuditEntry.objects.create(
        run=run,
        action="apply_fix",
        detail={"key": key.name, "fix_id": fix.id, "new_masked": m.masked},
    )

    # Re-probe with the corrected value — this is the "turns green" moment.
    return probe_and_classify_key(run, key, adapters=adapters, action="reprobe")


@transaction.atomic
def undo_fix(fix: Fix, adapters: dict | None = None) -> Finding:
    """Revert a previously applied fix and re-probe back to the prior verdict."""
    key = fix.config_key
    run = fix.run

    if not fix.undone:
        prev = fix.previous_state or {}
        key.secret_ciphertext = prev.get("ciphertext", "")
        key.masked_value = prev.get("masked", "")
        key.value_hint = prev.get("hint", "")
        key.kind = prev.get("kind", key.kind)
        key.is_probeable = prev.get("is_probeable", key.is_probeable)
        key.save()

        fix.undone = True
        fix.save(update_fields=["undone"])
        AuditEntry.objects.create(
            run=run, action="undo_fix", detail={"key": key.name, "fix_id": fix.id}
        )

    return probe_and_classify_key(run, key, adapters=adapters, action="reprobe")
