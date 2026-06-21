"""Ingestion orchestrator.

Takes a submitted config + codebase and turns it into a persisted, masked
inventory: ConfigKey rows (masked, classified) each linked to the UsageSites
where they appear in the code. The raw config text and file contents are NOT
persisted — only masked values and bounded code snippets.
"""

from __future__ import annotations

from django.db import transaction

from ..models import AuditEntry, ConfigKey, Run, UsageSite
from .config_parser import parse_config
from .masking import mask_value
from .usage_locator import locate_usages


@transaction.atomic
def ingest_run(
    run: Run,
    config_text: str,
    files: dict[str, str] | None = None,
    config_format: str = "",
    config_filename: str = "",
) -> Run:
    """Parse, mask, locate usages, and persist the inventory for a run."""
    files = files or {}
    fmt, parsed = parse_config(config_text, config_format, config_filename)
    run.config_format = fmt

    key_names = [p.name for p in parsed]
    usages = locate_usages(files, key_names)

    created = 0
    for p in parsed:
        m = mask_value(p.name, p.value)
        key = ConfigKey.objects.create(
            run=run,
            name=p.name,
            masked_value=m.masked,
            value_hint=m.hint,
            kind=m.kind,
            is_secret=m.is_secret,
            is_probeable=m.is_probeable,
        )
        sites = [
            UsageSite(
                config_key=key,
                file_path=h.file_path,
                line_number=h.line_number,
                usage_kind=h.usage_kind,
                snippet=h.snippet,
            )
            for h in usages.get(p.name, [])
        ]
        UsageSite.objects.bulk_create(sites)
        created += 1

    run.status = Run.Status.PARSED
    run.save(update_fields=["config_format", "status", "updated_at"])

    AuditEntry.objects.create(
        run=run,
        action="ingest",
        detail={
            "format": fmt,
            "keys": created,
            "probeable": run.keys.filter(is_probeable=True).count(),
            "files_scanned": len(files),
        },
    )
    return run
