"""Celery tasks.

Re-probing is exposed as an async task so a run can be re-checked later (the
're-probe drift' beat) without blocking a request. The interactive approve flow
re-probes synchronously for an immediate green; this task is for scheduled or
deferred re-checks.
"""

from __future__ import annotations

from celery import shared_task

from .models import Run
from .services.orchestrator import run_probes


@shared_task
def reprobe_run(run_id: str) -> dict:
    """Re-run all probes for a run and return the fresh findings summary."""
    run = Run.objects.get(id=run_id)
    run_probes(run)
    summary = {"correct": 0, "suspect": 0, "silently_wrong": 0}
    for f in run.findings.all():
        summary[f.classification] = summary.get(f.classification, 0) + 1
    return summary
