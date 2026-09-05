"""Ops-console backend (FastAPI).

Reaches integrations only through the typed clients (`clickup/`, `tools/`); core packages never
import this package (ADR-0002).

Loads `.env` the same way `brain/__init__.py` does. This matters beyond convenience: both
services verify the *same* JWT, so if only one of them read `.env` they would end up with
different `OPS_SECRET_KEY` values and every cross-service call would 401.
"""

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional — the backend runs fine without it (no .env autoload)
    pass
