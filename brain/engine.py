"""Engine seam — route an LLM prompt to the configured backend.

The brain's one place that actually calls an LLM. Swap the backend with the BRAIN_ENGINE env var:

    BRAIN_ENGINE=claude   (default)  ->  claude -p   (prompt on stdin)
    BRAIN_ENGINE=hermes              ->  hermes -z   (prompt as arg, final text out)

Local dev uses `claude`; a Hermes box sets `BRAIN_ENGINE=hermes`. Nothing else changes — this is the
engine-agnostic seam the extractors are built around.
"""

from __future__ import annotations

import os
import shutil
import subprocess


def run_llm(prompt: str, *, timeout: int = 300) -> str:
    """Send `prompt` to the configured engine and return its stdout text."""
    engine = os.environ.get("BRAIN_ENGINE", "claude").lower()

    if engine == "hermes":
        exe = shutil.which("hermes")
        if not exe:
            raise SystemExit("BRAIN_ENGINE=hermes but `hermes` is not on PATH.")
        # hermes -z: single prompt in (as an arg), final response text out, nothing else.
        proc = subprocess.run(
            [exe, "-z", prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=timeout,
        )
    else:
        exe = shutil.which("claude")
        if not exe:
            raise SystemExit("`claude` not on PATH. Install Claude Code, or set BRAIN_ENGINE=hermes.")
        proc = subprocess.run(
            [exe, "-p"],
            input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
        )

    if proc.returncode != 0:
        raise SystemExit(f"{engine} engine failed (exit {proc.returncode}):\n{proc.stderr.strip()}")
    return proc.stdout.strip()
