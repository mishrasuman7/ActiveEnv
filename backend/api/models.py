"""Data models for ActiveEnv.

A `Run` is one verification job: the user submits a config + codebase, we parse
it into `ConfigKey`s, locate where each key is used (`UsageSite`s), then in later
phases attach a `Finding` per key and record every action in the `AuditEntry`
log. Secrets are never stored in plaintext — only masked values + a small hint.
"""

import uuid

from django.db import models


class Run(models.Model):
    """One end-to-end verification job."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARSED = "parsed", "Parsed"          # config + usage inventoried
        INFERRED = "inferred", "Inferred"    # intent inferred (Phase 2)
        PROBED = "probed", "Probed"          # reality probed + classified (Phase 4)
        DONE = "done", "Done"

    class SourceType(models.TextChoices):
        PASTE = "paste", "Pasted"
        UPLOAD = "upload", "Uploaded"
        REPO = "repo", "Repo URL"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    source_type = models.CharField(
        max_length=16, choices=SourceType.choices, default=SourceType.PASTE
    )
    # The environment the user believes this config is for (prod/staging/dev).
    # Drives intent: "in prod this key must be live".
    target_environment = models.CharField(max_length=32, default="production")
    config_format = models.CharField(max_length=16, blank=True)  # env/python/yaml/json
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Run {self.id} ({self.status})"


class ConfigKey(models.Model):
    """A single config variable parsed from the submitted config."""

    class Kind(models.TextChoices):
        DATABASE_URL = "database_url", "Database URL"
        STRIPE_KEY = "stripe_key", "Stripe key"
        GITHUB_TOKEN = "github_token", "GitHub token"
        UNKNOWN = "unknown", "Unknown"

    run = models.ForeignKey(Run, related_name="keys", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    # Masked rendering, e.g. "sk_test_****ABCD" or "postgres://user:****@host/db".
    masked_value = models.CharField(max_length=512, blank=True)
    # A tiny non-sensitive hint used for classification (prefix, last4, scheme).
    value_hint = models.CharField(max_length=128, blank=True)
    kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.UNKNOWN)
    is_secret = models.BooleanField(default=True)
    is_probeable = models.BooleanField(default=False)
    # Fernet-encrypted real value, kept only for probeable keys so a probe /
    # re-probe can use it. Never returned by the API. Empty for non-probeable.
    secret_ciphertext = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        unique_together = ("run", "name")

    def __str__(self):
        return f"{self.name} ({self.kind})"


class UsageSite(models.Model):
    """Where and how a config key is referenced in the codebase."""

    config_key = models.ForeignKey(
        ConfigKey, related_name="usage_sites", on_delete=models.CASCADE
    )
    file_path = models.CharField(max_length=1024)
    line_number = models.PositiveIntegerField()
    usage_kind = models.CharField(max_length=64, blank=True)  # os.environ/getenv/settings/...
    # The surrounding code slice fed to Qwen for intent inference (bounded, not whole repo).
    snippet = models.TextField(blank=True)

    class Meta:
        ordering = ["file_path", "line_number"]

    def __str__(self):
        return f"{self.file_path}:{self.line_number}"


class Intent(models.Model):
    """What a config value is *supposed* to be, inferred by Qwen from usage.

    This is the "intent" half of the product — grounded in how the key is used
    in the codebase, not the value itself. The "reality" half (a probe result)
    is compared against this in Phase 4 to produce a Finding.
    """

    config_key = models.OneToOneField(
        ConfigKey, related_name="intent", on_delete=models.CASCADE
    )
    # The environment the value should belong to, given how it's used.
    expected_environment = models.CharField(max_length=32, default="any")
    # Structured expectations, e.g. {"stripe_mode": "live"} or {"db_role": "prod"}.
    expected_properties = models.JSONField(default=dict, blank=True)
    # Short phrase: what this value gates / controls.
    gates = models.CharField(max_length=255, blank=True)
    # One-sentence grounded reasoning (also the text streamed to the UI).
    rationale = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)
    grounded = models.BooleanField(default=False)  # was there real usage to ground on?
    model = models.CharField(max_length=64, blank=True)
    raw_response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Intent({self.config_key.name} -> {self.expected_environment})"


class Finding(models.Model):
    """The verdict for one key after intent vs. reality is compared (Phase 4)."""

    class Classification(models.TextChoices):
        CORRECT = "correct", "Correct"
        SUSPECT = "suspect", "Suspect"
        SILENTLY_WRONG = "silently_wrong", "Silently wrong"
        UNKNOWN = "unknown", "Unknown"

    run = models.ForeignKey(Run, related_name="findings", on_delete=models.CASCADE)
    config_key = models.OneToOneField(
        ConfigKey, related_name="finding", on_delete=models.CASCADE
    )
    classification = models.CharField(
        max_length=20,
        choices=Classification.choices,
        default=Classification.UNKNOWN,
    )
    expected = models.JSONField(default=dict, blank=True)   # inferred intent
    reality = models.JSONField(default=dict, blank=True)    # probe result
    evidence = models.TextField(blank=True)
    blast_radius = models.TextField(blank=True)
    proposed_fix = models.CharField(max_length=512, blank=True)
    confidence = models.FloatField(default=0.0)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.config_key.name}: {self.classification}"


class AuditEntry(models.Model):
    """Append-only log of every inference, probe, fix, and undo on a run."""

    run = models.ForeignKey(Run, related_name="audit", on_delete=models.CASCADE)
    action = models.CharField(max_length=64)
    detail = models.JSONField(default=dict, blank=True)
    undone = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M:%S}"
