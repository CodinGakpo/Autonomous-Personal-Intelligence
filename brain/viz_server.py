"""brain/viz_server.py — a tiny visual window into the brain.

Serves the real contents of `brain.db` as JSON, plus a self-contained HTML page that renders each
person's 6-axis capability radar and the action items linked to them. No build step, no auth, no extra
libraries — just FastAPI reading the store the same way `brain.query` does.

    uv run uvicorn brain.viz_server:app --port 8080
    # then open http://127.0.0.1:8080

The `/api/data` endpoint is reusable — the console can call it later to render the same thing in React.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from brain import ask, ingest, mail_ask, mail_ingest, profile, store
from brain.auth import CurrentUser
from brain.emailtool import _load_oauth_credentials, _token_path, mailbox_status
from brain.notify import notify

app = FastAPI(title="Agent OS Brain - Viz")
HERE = Path(__file__).resolve().parent


def get_user_conn(user: CurrentUser) -> Iterator[sqlite3.Connection]:
    """Per-request connection to *this user's own* SQLite file — the actual isolation
    boundary (see brain/store.py's connect()). Every endpoint except the unauthenticated
    legacy pages (GET /, GET /mail-tree) depends on this instead of calling store.connect()
    directly."""
    conn = store.connect(user_id=user)
    try:
        yield conn
    finally:
        conn.close()


ConnDep = Annotated[sqlite3.Connection, Depends(get_user_conn)]

# Lets the console frontend (a separate Vite dev server / origin) call this API directly.
_origins = os.environ.get("BRAIN_CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _fit(radar: dict[str, Any]) -> int | None:
    """Overall fit = mean of the radar axes (already role-weighted when ingested with a role)."""
    scores = [(v or {}).get("score") for v in radar.values() if isinstance(v, dict)]
    scores = [s for s in scores if isinstance(s, (int, float))]
    return round(sum(scores) / len(scores)) if scores else None


def _person(conn: Any, p: dict[str, Any]) -> dict[str, Any]:
    d = p["data"]
    radar = d.get("radar") or {}
    tasks = store.neighbors(conn, p["id"], "assigned_to", incoming=True)
    return {
        "id": p["id"],
        "name": p["title"],
        "kind": d.get("kind") or "person",
        "target_role": d.get("target_role"),
        "headline": d.get("headline"),
        "summary": d.get("summary"),
        "seniority": d.get("seniority"),
        "years": d.get("total_years_experience"),
        "fit_score": _fit(radar),
        "skills": d.get("skills") or [],
        "strengths": d.get("strengths") or [],
        "radar": radar,
        "roles": d.get("roles") or [],
        "education": d.get("education") or [],
        "flags": d.get("flags") or [],
        "needs_review": bool(p.get("needs_review")),
        "tasks": [
            {"name": t["title"], "due": t["data"].get("due_date"), "priority": t["data"].get("priority")}
            for t in tasks
        ],
    }


@app.get("/api/data")
def data(conn: ConnDep) -> dict[str, Any]:
    """Everything the page needs, straight from the caller's own brain.db."""
    people = [_person(conn, p) for p in store.all_of_type(conn, "person")]
    tasks = [
        {
            "name": t["title"],
            "assignee": t["data"].get("assignee"),
            "due": t["data"].get("due_date"),
            "priority": t["data"].get("priority"),
            "description": t["data"].get("description"),
            "needs_review": bool(t.get("needs_review")),
        }
        for t in store.all_of_type(conn, "task")
    ]
    meetings = [
        {"title": m["title"], "summary": m["summary"], "date": m["data"].get("meeting_date")}
        for m in store.all_of_type(conn, "meeting")
    ]
    return {"people": people, "tasks": tasks, "meetings": meetings}


class Question(BaseModel):
    question: str


@app.post("/api/ask")
def ask_brain(q: Question, conn: ConnDep) -> dict[str, Any]:
    """Natural-language question -> answer + the node path the brain walked (provenance)."""
    return ask.ask(conn, q.question)


ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


@app.post("/api/ingest_resume")
async def ingest_resume_upload(
    conn: ConnDep,
    file: UploadFile = File(...),
    role: str = Form(""),
    candidate: str = Form(""),
) -> Any:
    """Uploaded résumé (PDF/DOCX) -> the résumé parser -> a Person node in the brain.

    Reuses `brain.ingest.ingest_resume` verbatim; this endpoint only lands the upload on a temp path
    (the parser dispatches on file extension) and cleans it up after.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported file type '{suffix or '?'}'. Use PDF or DOCX."},
        )

    tmpdir = Path(tempfile.mkdtemp(prefix="brain_resume_"))
    # Never trust the uploaded filename for a disk path (path traversal) — only its
    # already-validated suffix.
    tmp = tmpdir / f"upload-{uuid.uuid4().hex}{suffix}"
    try:
        tmp.write_bytes(await file.read())
        kind = "candidate" if candidate else "person"
        out = ingest.ingest_resume(conn, tmp, role or "", kind)
        notify("candidate_added", name=out["name"], role=role or None, action=out["action"])
        return {"action": out["action"], "name": out["name"], "id": out["id"]}
    except (Exception, SystemExit) as exc:  # parser/ingest raise SystemExit on bad input
        return JSONResponse(status_code=400, content={"error": str(exc)})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _mail_children(conn: Any, parent_id: str) -> list[dict[str, Any]]:
    return [
        n for n in store.neighbors(conn, parent_id, "contains")
        if n["type"] in ("mail_category", "mail_topic", "mail_thread")
    ]


def _mail_node(conn: Any, node: dict[str, Any]) -> dict[str, Any]:
    children = [_mail_node(conn, c) for c in _mail_children(conn, node["id"])]
    out: dict[str, Any] = {
        "id": node["id"],
        "name": node["title"],
        "type": node["type"],
        "summary": node.get("summary"),
        # Set when the classifier wasn't sure which category this belonged in — the UI flags
        # these so a wrong call is findable instead of silently wrong.
        "needs_review": bool(node.get("needs_review")),
    }
    if node["type"] == "mail_thread":
        out["body"] = node["data"].get("body")
        out["source_uids"] = node["data"].get("source_uids") or []
        out["classification"] = node["data"].get("classification")
    if children:
        out["children"] = children
    return out


@app.get("/api/mail_tree")
def mail_tree(conn: ConnDep) -> dict[str, Any]:
    """The mail knowledge tree (mail_category -> mail_topic -> mail_thread) as nested JSON,
    rooted under a synthetic "Mail" node so the page always has a single root to render."""
    categories = store.all_of_type(conn, "mail_category")
    return {
        "id": "mail:root",
        "name": "Mail",
        "type": "root",
        "children": [_mail_node(conn, c) for c in categories],
    }


class MailReloadRequest(BaseModel):
    since_minutes: int


@app.post("/api/mail/reload")
def mail_reload(body: MailReloadRequest, user: CurrentUser) -> dict[str, Any]:
    """Ingest unread mail from the last `since_minutes` minutes into the caller's own tree."""
    results = mail_ingest.run(since_minutes=body.since_minutes, user_id=user)
    return {"processed": len(results), "results": results}


@app.post("/api/mail/reload/stream")
def mail_reload_stream(body: MailReloadRequest, user: CurrentUser) -> StreamingResponse:
    """Ingest unread mail, streaming one NDJSON progress event per step.

    Same work as /api/mail/reload, but the caller finds out what is happening while it happens
    — a batch of ten emails is twenty-odd LLM round-trips, and a single blocking request tells
    the UI nothing until it is over.
    """

    def events() -> Iterator[str]:
        try:
            for event in mail_ingest.run_iter(since_minutes=body.since_minutes, user_id=user):
                yield json.dumps(event) + "\n"
        except (Exception, SystemExit) as exc:
            # A failure mid-stream still has to reach the client: the response is already 200
            # by the time it happens, so it travels as a terminal event, not a status code.
            yield json.dumps({"stage": "failed", "error": str(exc)}) + "\n"

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        # Stops a proxy buffering the whole response and defeating the point of streaming.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/mail/status")
def mail_status(user: CurrentUser) -> dict[str, Any]:
    """Whether this user's mailbox can actually be authenticated as.

    Checks the credentials really load and refresh rather than that a file exists — a token
    can be present and still be revoked, expired past refresh, or never have been a real
    grant, and reporting those as "connected" only defers the failure to the next fetch.
    """
    return mailbox_status(user)


@app.post("/api/mail/disconnect")
def mail_disconnect(user: CurrentUser) -> dict[str, Any]:
    """Revoke this user's cached OAuth token so their mailbox needs to be reconnected."""
    token_path = _token_path(user)
    if token_path.exists():
        token_path.unlink()
    meta = token_path.with_name("meta.json")
    if meta.exists():
        meta.unlink()  # the cached mailbox address belongs to the grant being revoked
    return mailbox_status(user)


@app.post("/api/mail/connect")
def mail_connect(user: CurrentUser) -> dict[str, Any]:
    """Run the interactive OAuth consent flow for this user and cache the resulting token.

    This server and the browser hitting it are on the same machine (local dev), so opening
    the consent page here — the same thing `emailtool.py auth` does from a terminal — reaches
    the person clicking "Connect" without them needing a terminal at all. Blocks until they
    complete (or abandon) the browser consent flow.
    """
    try:
        _load_oauth_credentials(interactive=True, user_id=user)
    except Exception as exc:
        # Without this the consent page says "you may close this window" while the server 500s
        # and the UI just keeps showing "not connected" with no explanation of why.
        return JSONResponse(
            status_code=502,
            content={"connected": False, "error": f"Could not complete sign-in: {exc}"},
        )
    return mailbox_status(user)


class ProfileDetail(BaseModel):
    key: str
    value: str


class MailAskRequest(BaseModel):
    question: str
    profile_details: list[ProfileDetail] = []


@app.post("/api/mail/ask")
def mail_ask_endpoint(body: MailAskRequest, conn: ConnDep) -> Any:
    """Natural-language question over the caller's own ingested mail tree -> plain-text answer."""
    details = [d.model_dump() for d in body.profile_details]
    try:
        return mail_ask.ask_mail(conn, body.question, details)
    except SystemExit as exc:
        # call_openrouter raises SystemExit when every OPENROUTER_API_KEYS entry is
        # exhausted/rejected.
        return JSONResponse(status_code=502, content={"error": str(exc)})


class ProfileDetailIn(BaseModel):
    key: str
    value: str = ""


class ProfileUpdate(BaseModel):
    details: list[ProfileDetailIn] = []


@app.get("/api/profile")
def get_profile(conn: ConnDep) -> dict[str, Any]:
    """This user's "About you" details, plus which of them the mail pipeline treats as
    identifiers when scanning attachments."""
    details = profile.load_profile(conn)
    return {"details": details, "identifiers": profile.identifiers_from_profile(details)}


@app.put("/api/profile")
def put_profile(body: ProfileUpdate, conn: ConnDep) -> dict[str, Any]:
    """Replace the stored profile. Stored server-side rather than in the browser because mail
    ingestion — which is where attachments are scanned — runs headless.

    Changing the identifiers re-scans already-ingested attachments: findings are frozen at
    ingest, so adding your roll number afterwards would otherwise leave every shortlist that
    arrived earlier still claiming you are not on it.
    """
    before = set(profile.identifiers_from_profile(profile.load_profile(conn)))
    saved = profile.save_profile(conn, [d.model_dump() for d in body.details])
    identifiers = profile.identifiers_from_profile(saved)

    rescanned: list[dict[str, Any]] = []
    if set(identifiers) != before:
        rescanned = mail_ingest.rescan_attachments(conn, mail_ingest.load_config())

    return {"details": saved, "identifiers": identifiers, "rescanned": rescanned}


@app.post("/api/mail/attachments/rescan")
def mail_rescan_attachments(conn: ConnDep) -> dict[str, Any]:
    """Re-check every cached attachment against the current identifiers, on demand."""
    changed = mail_ingest.rescan_attachments(conn, mail_ingest.load_config())
    return {"changed": changed}


def _thread_path(conn: Any, thread_id: str) -> tuple[str | None, str | None]:
    """The (category, topic) a thread currently sits under, by walking `contains` upwards."""
    topics = store.neighbors(conn, thread_id, "contains", incoming=True)
    if not topics:
        return None, None
    topic = topics[0]
    categories = store.neighbors(conn, topic["id"], "contains", incoming=True)
    return (categories[0]["title"] if categories else None), topic["title"]


@app.get("/api/mail/review")
def mail_review(conn: ConnDep) -> dict[str, Any]:
    """Threads whose category the classifier wasn't confident about.

    The mindmap flags these individually, but finding them there means expanding the tree node
    by node — this gives the UI a single actionable list to work through.
    """
    items: list[dict[str, Any]] = []
    for thread in store.all_of_type(conn, "mail_thread"):
        if not thread.get("needs_review"):
            continue
        category, topic = _thread_path(conn, thread["id"])
        classification = thread["data"].get("classification") or {}
        items.append(
            {
                "id": thread["id"],
                "name": thread["title"],
                "summary": thread.get("summary"),
                "category": category,
                "topic": topic,
                "llm_category": classification.get("llm_category"),
                "keyword_category": classification.get("keyword_category"),
                "scores": classification.get("scores") or {},
            }
        )
    categories = [c["title"] for c in store.all_of_type(conn, "mail_category")]
    return {"threads": items, "categories": categories}


class MailReclassifyRequest(BaseModel):
    thread_id: str
    category: str
    topic: str | None = None


@app.post("/api/mail/reclassify")
def mail_reclassify(body: MailReclassifyRequest, conn: ConnDep) -> Any:
    """Move one mail thread under a different category (and optionally a different topic).

    The correction is authoritative: it clears the review flag and is recorded on the thread so
    the classifier can learn from it rather than refiling the same mail wrongly next time.
    """
    thread = store.get(conn, body.thread_id)
    if thread is None or thread["type"] != "mail_thread":
        return JSONResponse(status_code=404, content={"error": "Thread not found"})

    category = body.category.strip()
    if not category:
        return JSONResponse(status_code=400, content={"error": "category must not be empty"})

    # Default to the thread's current topic name so a category-only move keeps its grouping.
    topic = (body.topic or "").strip()
    if not topic:
        parents = store.neighbors(conn, body.thread_id, "contains", incoming=True)
        topic = parents[0]["title"] if parents else (thread["title"] or "Untitled")

    topic_id = mail_ingest.ensure_topic(conn, category, topic)

    payload = dict(thread["data"])
    classification = dict(payload.get("classification") or {})
    classification.update(
        {
            "category": category,
            "confidence": "high",
            "corrected_by_user": True,
            # What the classifier had said, kept so a future run can learn from the correction.
            "auto_category": classification.get("category"),
        }
    )
    payload["classification"] = classification

    store.upsert(
        conn,
        "mail_thread",
        payload,
        title=thread["title"],
        summary=thread["summary"],
        source=thread["source"],
        needs_review=False,
    )
    mail_ingest.reparent_thread(conn, body.thread_id, topic_id)
    store.add_edge(conn, topic_id, body.thread_id, "contains")
    # Teach the classifier from the correction, so similar mail isn't misfiled the same way.
    learned = mail_ingest.learn_category_keywords(conn, category, thread["title"] or "")
    pruned = mail_ingest.prune_empty_mail_nodes(conn)

    return {
        "thread_id": body.thread_id,
        "category": category,
        "topic": topic,
        "topic_id": topic_id,
        "pruned": pruned,
        "learned_keywords": learned,
    }


@app.get("/mail-tree")
def mail_tree_page() -> FileResponse:
    return FileResponse(HERE / "mail_tree.html")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "viz.html")
