"""Runtime configuration, read from the environment.

Integration tokens are not required at import time — missing ones are reported by the health
endpoint rather than crashing the app. The database URL and secret key DO have dev defaults so
the app boots locally; override both in any real deployment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Local default: a Postgres on localhost. In Docker this is overridden to the `db` service.
DEFAULT_DATABASE_URL = "postgresql+psycopg://ops:ops@localhost:5433/ops_console"


@dataclass(frozen=True)
class Settings:
    clickup_token: str | None
    slack_bot_token: str | None
    fathom_api_key: str | None
    # Seed admin login, created on startup if absent (see db.seed_admin).
    admin_email: str
    admin_password: str
    clickup_employees_list_id: str | None
    database_url: str
    secret_key: str
    # The brain service (brain/viz_server.py) — chat.py proxies mail Q&A there, forwarding the
    # same bearer token this request carried (see console/backend/chat.py).
    brain_api_base_url: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            clickup_token=os.environ.get("CLICKUP_TOKEN"),
            slack_bot_token=os.environ.get("SLACK_BOT_TOKEN"),
            fathom_api_key=os.environ.get("FATHOM_API_KEY"),
            admin_email=os.environ.get("OPS_ADMIN_EMAIL", "admin@agent-os.local"),
            admin_password=os.environ.get("OPS_ADMIN_PASSWORD", "changeme"),
            clickup_employees_list_id=os.environ.get("CLICKUP_EMPLOYEES_LIST_ID"),
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            secret_key=os.environ.get("OPS_SECRET_KEY", "dev-secret-change-me"),
            brain_api_base_url=os.environ.get("BRAIN_API_BASE_URL", "http://localhost:8080"),
        )


def get_settings() -> Settings:
    """FastAPI dependency. Re-reads env each call so tests can override freely."""
    return Settings.from_env()
