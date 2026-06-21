"""Run orchestration: probe every probeable key, classify, persist findings.

This is the "plan probes → execute probes → compare & classify → explain" middle
of the pipeline. Probe adapters are injectable so the whole flow is testable
without a live database or network.
"""

from __future__ import annotations

from django.db import transaction

from ..models import AuditEntry, Finding, Run
from .classify import classify
from .prober import probe_key


@transaction.atomic
def run_probes(run: Run, adapters: dict | None = None) -> Run:
    """Probe + classify every probeable key on a run."""
    counts = {"correct": 0, "suspect": 0, "silently_wrong": 0}

    for key in run.keys.filter(is_probeable=True):
        evidence = probe_key(key, adapters=adapters)
        intent = getattr(key, "intent", None)
        result = classify(key, intent, evidence, run.target_environment)

        Finding.objects.update_or_create(
            config_key=key, defaults={"run": run, **result}
        )
        counts[result["classification"]] = counts.get(result["classification"], 0) + 1
        AuditEntry.objects.create(
            run=run,
            action="probe",
            detail={
                "key": key.name,
                "kind": key.kind,
                "classification": result["classification"],
                "reachable": evidence.reachable,
            },
        )

    run.status = Run.Status.PROBED
    run.save(update_fields=["status", "updated_at"])
    AuditEntry.objects.create(run=run, action="probe_run", detail=counts)
    return run
