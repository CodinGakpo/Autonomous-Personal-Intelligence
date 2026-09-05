"""Persisted mail-chat sessions.

console/backend owns session/message CRUD and ownership checks (it already owns `users`); the
actual Q&A logic stays in the brain service. Posting a message proxies to brain's
`/api/mail/ask`, forwarding the *same* bearer token this request carried so brain resolves the
same user and answers from that user's own ingested mail (see brain/viz_server.py's per-user
isolation) — the frontend never talks to brain directly for chat (ADR-0002 in spirit: one
service, one auth check, one place that commits what was said).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from console.backend.auth import CurrentUser
from console.backend.config import Settings, get_settings
from console.backend.db import get_db
from console.backend.models import ChatMessage, ChatSession

router = APIRouter(prefix="/chat", tags=["chat"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]

_TITLE_MAX_LEN = 60


class SessionOut(BaseModel):
    id: int
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class SessionWithMessagesOut(SessionOut):
    messages: list[MessageOut]


class RenameRequest(BaseModel):
    title: str


class ProfileDetail(BaseModel):
    key: str
    value: str


class PostMessageRequest(BaseModel):
    question: str
    profile_details: list[ProfileDetail] = []


def _get_owned_session(db: DbDep, session_id: int, user_id: int) -> ChatSession:
    """404 (not 403) for a session that doesn't exist OR belongs to someone else — never
    reveal whether another user's session id exists."""
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session not found")
    return session


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(db: DbDep, user: CurrentUser) -> ChatSession:
    session = ChatSession(user_id=user.id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(db: DbDep, user: CurrentUser) -> list[ChatSession]:
    return list(
        db.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == user.id)
            .order_by(ChatSession.updated_at.desc())
        )
    )


@router.get("/sessions/{session_id}", response_model=SessionWithMessagesOut)
def get_session(session_id: int, db: DbDep, user: CurrentUser) -> ChatSession:
    return _get_owned_session(db, session_id, user.id)


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def rename_session(
    session_id: int, body: RenameRequest, db: DbDep, user: CurrentUser
) -> ChatSession:
    session = _get_owned_session(db, session_id, user.id)
    session.title = body.title.strip()[:_TITLE_MAX_LEN] or None
    db.commit()
    db.refresh(session)
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int, db: DbDep, user: CurrentUser) -> None:
    session = _get_owned_session(db, session_id, user.id)
    db.delete(session)
    db.commit()


@router.post("/sessions/{session_id}/messages", response_model=MessageOut)
def post_message(
    session_id: int,
    body: PostMessageRequest,
    db: DbDep,
    user: CurrentUser,
    settings: SettingsDep,
    authorization: Annotated[str, Header()] = "",
) -> ChatMessage:
    session = _get_owned_session(db, session_id, user.id)
    question = body.question.strip()
    if not question:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "question must not be empty")

    user_message = ChatMessage(session_id=session.id, role="user", content=question)
    db.add(user_message)
    db.commit()

    try:
        resp = httpx.post(
            f"{settings.brain_api_base_url}/api/mail/ask",
            json={
                "question": question,
                "profile_details": [d.model_dump() for d in body.profile_details],
            },
            headers={"Authorization": authorization} if authorization else {},
            timeout=120,
        )
        resp.raise_for_status()
        answer = resp.json().get("answer", "")
    except httpx.HTTPError as exc:
        # Don't persist a broken assistant turn — the user message stays (it was really
        # asked), but a retry shouldn't leave a permanently-wrong answer in history.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Couldn't get an answer: {exc}"
        ) from exc

    if session.title is None:
        session.title = question[:_TITLE_MAX_LEN]
    # `onupdate=func.now()` only fires on an UPDATE of this row itself — a new ChatMessage row
    # doesn't touch it, so bump it explicitly to keep the sidebar's "most recent" ordering
    # accurate on every message, not just the first.
    session.updated_at = datetime.now(UTC)

    assistant_message = ChatMessage(session_id=session.id, role="assistant", content=answer)
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return assistant_message
