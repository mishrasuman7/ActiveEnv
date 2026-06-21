"""Run orchestration: probe every probeable key, classify, persist findings.

This is the "plan probes → execute probes → compare & classify → explain" middle
of the pipeline. Probe adapters are injectable so the whole flow is testable
without a live database or network.
"""

from __future__ import annotations

from django.db import transaction

from ..models import AuditEntry, ConfigKey, Finding, Run
from .classify import CORRECT, classify
from .prober import probe_key


def probe_and_classify_key(
    run: Run, key: ConfigKey, adapters: dict | None = None, *, action: str = "probe"
) -> Finding:
    """Probe one key, classify intent vs reality, and upsert its Finding.

    Shared by the initial run and by re-probes after a fix is applied/undone.
    A finding is `resolved` when reality matches intent (classification correct).
    """
    evidence = probe_key(key, adapters=adapters)
    intent = getattr(key, "intent", None)
    result = classify(key, intent, evidence, run.target_environment)
    result["resolved"] = result["classification"] == CORRECT

    finding, _ = Finding.objects.update_or_create(
        config_key=key, defaults={"run": run, **result}
    )
    AuditEntry.objects.create(
        run=run,
        action=action,
        detail={
            "key": key.name,
            "kind": key.kind,
            "classification": result["classification"],
            "reachable": evidence.reachable,
        },
    )
    return finding


@transaction.atomic
def run_probes(run: Run, adapters: dict | None = None) -> Run:
    """Probe + classify every probeable key on a run."""
    counts = {"correct": 0, "suspect": 0, "silently_wrong": 0}

    for key in run.keys.filter(is_probeable=True):
        finding = probe_and_classify_key(run, key, adapters=adapters)
        counts[finding.classification] = counts.get(finding.classification, 0) + 1

    run.status = Run.Status.PROBED
    run.save(update_fields=["status", "updated_at"])
    AuditEntry.objects.create(run=run, action="probe_run", detail=counts)
    return run
