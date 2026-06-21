"""
Alibaba Cloud proof-of-use — REQUIRED hackathon artifact.

This file demonstrates ActiveEnv calling a **Qwen** model on **Alibaba Cloud
Model Studio** (DashScope) via its OpenAI-compatible endpoint. The intent
inference and fix-proposal stages of the agent use this exact client.

Run:
    # from repo root, with .env populated (DASHSCOPE_API_KEY set)
    python backend/alibaba_proof.py

Expected: the model returns a short confirmation string, proving the API call
reached Alibaba Cloud and a Qwen model answered.
"""

import os
import sys
from pathlib import Path

# Load .env from repo root if present (so this runs standalone, no Django).
try:
    import environ

    environ.Env.read_env(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # environ not installed when run outside the venv
    pass

from openai import OpenAI  # noqa: E402

API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
BASE_URL = os.environ.get(
    "QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
)
MODEL = os.environ.get("QWEN_MODEL", "qwen-plus")


def main() -> int:
    if not API_KEY:
        print(
            "DASHSCOPE_API_KEY is not set.\n"
            "Get one from Alibaba Cloud Model Studio -> API-KEY, put it in .env, "
            "then re-run. (This file is the Alibaba Cloud proof-of-use artifact.)"
        )
        return 1

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are the Qwen model powering ActiveEnv on Alibaba Cloud.",
            },
            {
                "role": "user",
                "content": "Reply with exactly: ActiveEnv is live on Alibaba Cloud Model Studio.",
            },
        ],
        temperature=0,
    )
    answer = resp.choices[0].message.content.strip()
    print(f"[Qwen / {MODEL} @ Alibaba Cloud Model Studio] -> {answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
