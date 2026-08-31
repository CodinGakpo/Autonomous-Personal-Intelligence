"""brain/viz_server.py — a tiny visual window into the brain.

Serves the real contents of `brain.db` as JSON, plus a self-contained HTML page that renders each
person's 6-axis capability radar and the action items linked to them. No build step, no auth, no extra
libraries — just FastAPI reading the store the same way `brain.query` does.

    uv run uvicorn brain.viz_server:app --port 8080
    # then open http://127.0.0.1:8080

The `/api/data` endpoint is reusable — the console can call it later to render the same thing in React.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from brain import ask, ingest, mail_ingest, store
from brain.emailtool import _token_path
from brain.notify import notify

app = FastAPI(title="Agent OS Brain - Viz")
HERE = Path(__file__).resolve().parent

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
def data() -> dict[str, Any]:
    """Everything the page needs, straight from brain.db."""
    conn = store.connect()
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
def ask_brain(q: Question) -> dict[str, Any]:
    """Natural-language question -> answer + the node path the brain walked (provenance)."""
    conn = store.connect()
    return ask.ask(conn, q.question)


ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


@app.post("/api/ingest_resume")
async def ingest_resume_upload(
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
        conn = store.connect()
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
    }
    if node["type"] == "mail_thread":
        out["body"] = node["data"].get("body")
        out["source_uids"] = node["data"].get("source_uids") or []
    if children:
        out["children"] = children
    return out


@app.get("/api/mail_tree")
def mail_tree() -> dict[str, Any]:
    """The mail knowledge tree (mail_category -> mail_topic -> mail_thread) as nested JSON,
    rooted under a synthetic "Mail" node so the page always has a single root to render."""
    conn = store.connect()
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
def mail_reload(body: MailReloadRequest) -> dict[str, Any]:
    """Ingest unread mail from the last `since_minutes` minutes into the tree."""
    results = mail_ingest.run(since_minutes=body.since_minutes)
    return {"processed": len(results), "results": results}


@app.get("/api/mail/status")
def mail_status() -> dict[str, Any]:
    """Whether the mailbox has valid credentials cached (app password or an OAuth token)."""
    connected = bool(os.environ.get("EMAIL_APP_PASSWORD")) or _token_path().exists()
    return {"connected": connected}


@app.post("/api/mail/disconnect")
def mail_disconnect() -> dict[str, Any]:
    """Revoke the cached OAuth token so the mailbox needs `emailtool.py auth` again.

    Only affects the OAuth token cache — if EMAIL_APP_PASSWORD is set, that login path is
    unaffected (there's nothing to revoke locally for it).
    """
    token_path = _token_path()
    if token_path.exists():
        token_path.unlink()
    return {"connected": mail_status()["connected"]}


@app.get("/mail-tree")
def mail_tree_page() -> FileResponse:
    return FileResponse(HERE / "mail_tree.html")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "viz.html")
