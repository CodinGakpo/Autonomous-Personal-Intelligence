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

