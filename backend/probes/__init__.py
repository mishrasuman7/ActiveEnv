"""Read-only probe library for ActiveEnv.

Each probe takes a credential, connects/authenticates against the real system,
observes the truth (never writes), and returns a normalized `Evidence` object
with every secret masked. This package is pure Python (no Django) so it can be
imported by both the Django orchestrator and the standalone config-probe-mcp
server.
"""

from .evidence import Evidence
from .database import probe_database
from .github_probe import probe_github_token
from .stripe_probe import probe_stripe_key

__all__ = [
    "Evidence",
    "probe_database",
    "probe_stripe_key",
    "probe_github_token",
]
