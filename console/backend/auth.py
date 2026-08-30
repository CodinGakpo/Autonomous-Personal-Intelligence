"""Auth: DB-backed login, per-user JWT tokens, and the dependencies that guard routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from console.backend.config import Settings, get_settings
from console.backend.db import get_db
from console.backend.models import User
from console.backend.security import create_token, decode_token, hash_password, verify_password

router = APIRouter(tags=["auth"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    token: str


class CreateUserRequest(BaseModel):
    email: str
    password: str
    # Valid roles: admin | team_lead | developer | hr  (ADR-0003)
    role: str = "developer"


class UserOut(BaseModel):
    id: int
    email: str
    role: str


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, settings: SettingsDep, db: DbDep) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return TokenResponse(token=create_token(user.id, settings.secret_key))


def get_current_user(
    settings: SettingsDep,
    db: DbDep,
    authorization: Annotated[str, Header()] = "",
) -> User:
    """Dependency: resolve the authenticated user from the bearer token, or 401."""
    scheme, _, token = authorization.partition(" ")
    user_id = decode_token(token, settings.secret_key) if scheme.lower() == "bearer" else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    """Convenience dep — used by POST /auth/users (Law 4, ADR-0003). Admin only."""
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


@router.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.post("/auth/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    db: DbDep,
    _admin: Annotated[User, Depends(require_admin)],
) -> User:
    if db.scalar(select(User).where(User.email == body.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")
    user = User(email=body.email, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
