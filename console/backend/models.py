"""Database models. The console's only persisted table for v1 is `users` (login accounts).

People onboarded into the org still live in ClickUp (source of truth); this table is purely
auth identities for the console.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="admin")
    is_active: Mapped[bool] = mapped_column(default=True)
