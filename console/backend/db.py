"""Database engine, session dependency, and admin seeding.

The engine is configured once at app startup (`configure_engine`) from the active settings, so
tests can point it at a throwaway SQLite file while production uses Postgres — same code path.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from console.backend.config import Settings
from console.backend.models import Base, User
from console.backend.security import hash_password

_session_factory: sessionmaker[Session] | None = None


def configure_engine(database_url: str) -> None:
    """(Re)build the engine + session factory and create tables. Idempotent."""
    global _session_factory
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    _session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)


def _factory() -> sessionmaker[Session]:
    if _session_factory is None:
        raise RuntimeError("Database not configured — call configure_engine() first.")
    return _session_factory


def get_db() -> Iterator[Session]:
    """FastAPI dependency: a request-scoped session."""
    db = _factory()()
    try:
        yield db
    finally:
        db.close()


def seed_admin(settings: Settings) -> None:
    """Ensure the configured admin login exists (idempotent)."""
    with _factory()() as db:
        existing = db.scalar(select(User).where(User.email == settings.admin_email))
        if existing is None:
            db.add(
                User(
                    email=settings.admin_email,
                    password_hash=hash_password(settings.admin_password),
                    role="admin",
                )
            )
            db.commit()


# ---------------------------------------------------------------------------
# Demo-only seed data — all 9 team members as login accounts.
# Called when create_app(demo_seed=True) is used (i.e. _demo_server.py).
# Password is "demo" for every account — NOT for production use.
# ---------------------------------------------------------------------------

_DEMO_USERS: list[tuple[str, str]] = [
    # (email, access_role)
    ("fenil@agent-os.local", "admin"),
    ("usman@agent-os.local", "admin"),
    ("manikandan@agent-os.local", "team_lead"),
    ("hirak@agent-os.local", "developer"),
    ("sajal@agent-os.local", "developer"),
    ("pruthvik@agent-os.local", "developer"),
    ("ayush@agent-os.local", "developer"),
    ("sudeep@agent-os.local", "developer"),
    ("yogesh@agent-os.local", "developer"),
]


def seed_demo_employees() -> None:
    """Seed all team members as User login records (demo only, password='demo')."""
    _pw = hash_password("demo")
    with _factory()() as db:
        for email, role in _DEMO_USERS:
            if db.scalar(select(User).where(User.email == email)) is None:
                db.add(User(email=email, password_hash=_pw, role=role, is_active=True))
        db.commit()

