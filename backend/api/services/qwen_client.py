"""Qwen client — thin wrapper over Alibaba Cloud Model Studio.

Model Studio exposes an OpenAI-compatible API, so we use the `openai` SDK
pointed at the DashScope base URL. The wrapper is deliberately small and
injectable: callers can pass a fake client in tests, so the whole intent layer
is testable without a real API key.
"""

from __future__ import annotations

import json

from django.conf import settings


class QwenNotConfigured(RuntimeError):
    """Raised when an inference is attempted without DASHSCOPE_API_KEY set."""


class QwenClient:
    """Wraps a single JSON-returning chat completion against Qwen."""

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self.api_key = api_key or settings.QWEN_API_KEY
        self.base_url = base_url or settings.QWEN_BASE_URL
        self.model = model or settings.QWEN_MODEL
        if not self.api_key:
            raise QwenNotConfigured(
                "DASHSCOPE_API_KEY is not set — add it to .env to run real inference."
            )
        # Imported lazily so the module loads even if openai isn't installed yet.
        from openai import OpenAI

        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def complete_json(self, system: str, user: str, *, temperature: float = 0.0):
        """Return (parsed_dict, raw_text) from a JSON-mode completion."""
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        return _safe_json(raw), raw


def get_client() -> QwenClient:
    """Factory for a settings-configured client (raises if no key)."""
    return QwenClient()


def _safe_json(text: str) -> dict:
    """Parse a JSON object, tolerating a stray code fence if the model adds one."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        # drop a leading "json" language tag if present
        if "\n" in text:
            first, rest = text.split("\n", 1)
            if first.strip().lower() in ("json", ""):
                text = rest
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}
