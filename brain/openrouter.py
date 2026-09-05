"""brain/openrouter.py — the mail pipeline's LLM seam: OpenRouter with free-tier key rotation.

Separate from brain/engine.py (which shells out to a local CLI). The mail pipeline needs a real
HTTP LLM call, and needs to survive a single free-tier key running dry mid-run — so this module
tries each key in OPENROUTER_API_KEYS in order and rotates forward on a 401/402/429 response.
"""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
# The default text model has no image support, so vision uses its own.
DEFAULT_VISION_MODEL = "meta-llama/llama-3.2-11b-vision-instruct:free"
TIMEOUT_S = 120

# Status codes that mean "this key is done" — rotate to the next one rather than failing outright.
ROTATE_ON = {401, 402, 429}


def _url() -> str:
    """The chat-completions endpoint. OPENROUTER_BASE_URL exists so the end-to-end suite can
    point this at a local stub — the LLM hop is otherwise unmockable across a process
    boundary. Unset in normal use, which keeps the real OpenRouter endpoint."""
    base = os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    return f"{base}/chat/completions"


# Back-compat for callers/tests that import the constant directly.
OPENROUTER_URL = f"{DEFAULT_BASE_URL}/chat/completions"


def _keys() -> list[str]:
    raw = os.environ.get("OPENROUTER_API_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise SystemExit(
            "Set OPENROUTER_API_KEYS (comma-separated) in .env to use the mail pipeline."
        )
    return keys


def call_openrouter_vision(prompt: str, image_data_url: str, *, model: str | None = None) -> str:
    """Ask a vision-capable model about one image.

    Same key rotation as `call_openrouter`; only the message shape differs (OpenAI-compatible
    content parts). The model is separate because the default text model is a small one with
    no image support.
    """
    model = model or os.environ.get("OPENROUTER_VISION_MODEL", DEFAULT_VISION_MODEL)
    return _post(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        ],
        model,
    )


def call_openrouter(prompt: str, *, model: str | None = None) -> str:
    """Send `prompt` as a single user message; return the model's text reply.

    Tries each key in OPENROUTER_API_KEYS in turn, rotating forward whenever a key is
    rejected or rate/quota-limited (401/402/429), so one exhausted free-tier key doesn't
    stop the run.
    """
    model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    return _post([{"role": "user", "content": prompt}], model)


def _post(messages: list[dict[str, Any]], model: str) -> str:
    """POST a chat completion, rotating through keys. Shared by the text and vision helpers."""
    keys = _keys()
    last_error = ""

    for key in keys:
        try:
            response = requests.post(
                _url(),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages},
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
