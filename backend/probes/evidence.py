"""Normalized probe result.

Every probe returns one of these, regardless of adapter, so the classifier in
Phase 4 can compare intent vs. reality uniformly. `observed` holds the
adapter-specific facts; `masked_input` is the safe-to-display rendering of what
was probed (the raw credential is never included).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Evidence:
    probe: str                       # "database" | "stripe_key" | "github_token"
    ok: bool                         # did we successfully observe reality?
    reachable: bool                  # did we connect/authenticate at all?
    observed: dict = field(default_factory=dict)  # normalized facts from reality
    summary: str = ""                # human one-liner
    masked_input: str = ""           # masked rendering of what was probed
    error: str = ""                  # populated on failure

    def to_dict(self) -> dict:
        return asdict(self)
