"""brain/openrouter.py — the mail pipeline's LLM seam: OpenRouter with free-tier key rotation.

Separate from brain/engine.py (which shells out to a local CLI). The mail pipeline needs a real
HTTP LLM call, and needs to survive a single free-tier key running dry mid-run — so this module
tries each key in OPENROUTER_API_KEYS in order and rotates forward on a 401/402/429 response.
"""

from __future__ import annotations

import os

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
TIMEOUT_S = 120

# Status codes that mean "this key is done" — rotate to the next one rather than failing outright.
ROTATE_ON = {401, 402, 429}


def _keys() -> list[str]:
    raw = os.environ.get("OPENROUTER_API_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise SystemExit(
            "Set OPENROUTER_API_KEYS (comma-separated) in .env to use the mail pipeline."
        )
    return keys


def call_openrouter(prompt: str, *, model: str | None = None) -> str:
    """Send `prompt` as a single user message; return the model's text reply.

    Tries each key in OPENROUTER_API_KEYS in turn, rotating forward whenever a key is
    rejected or rate/quota-limited (401/402/429), so one exhausted free-tier key doesn't
    stop the run.
    """
    model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    keys = _keys()
    last_error = ""

    for key in keys:
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                timeout=TIMEOUT_S,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            continue

        if response.status_code in ROTATE_ON:
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            continue

        response.raise_for_status()
        data = response.json()
        choices = data.get("choices")
        if not choices:
            # Seen in practice: OpenRouter can return HTTP 200 with an embedded
            # upstream-provider error instead of the normal choices payload.
            last_error = f"unexpected response shape (no choices): {str(data)[:300]}"
            continue
        content = choices[0].get("message", {}).get("content")
        if not content:
            # Seen in practice: some free-tier models return content: null (e.g. a
            # refusal or an empty completion) instead of raising an HTTP error.
            last_error = f"empty/null content in response: {str(data)[:300]}"
            continue
        return content.strip()

    raise SystemExit(f"All OPENROUTER_API_KEYS exhausted or rejected. Last error: {last_error}")
