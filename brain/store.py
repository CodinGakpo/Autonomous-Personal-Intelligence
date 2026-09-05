"""brain/store.py — the Plan B entity graph, persisted in SQLite.

The write path's *memory*. The extractors (LLM) produce candidate nodes, the resolver decides —
deterministically — create / update / review, and this store applies that decision idempotently.

    nodes = `entities` (person, task, meeting, …)   |   relations = `edges` (typed, directed)

Idempotency comes from the resolver's stable key + a lookup, never from the LLM returning identical
text (per the Plan B write-path design). Pure stdlib: sqlite3 + json. No network, no LLM.

Location: `brain/brain.db` by default, or the BRAIN_DB env var.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain.resolver import Resolution, resolve

DEFAULT_DB = Path(__file__).resolve().parent / "brain.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id           TEXT PRIMARY KEY,
    type         TEXT NOT NULL,
    natural_key  TEXT,
    title        TEXT,
    summary      TEXT,
    data         TEXT,                       -- full JSON payload (radar / task fields / …)
    source       TEXT,                       -- provenance: file path, meeting, clickup id
    needs_review INTEGER NOT NULL DEFAULT 0,  -- 1 = resolver flagged a possible duplicate
    created_at   TEXT,
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);

CREATE TABLE IF NOT EXISTS edges (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    src_id     TEXT NOT NULL,
    dst_id     TEXT NOT NULL,
    relation   TEXT NOT NULL,                 -- e.g. 'assigned_to', 'from_meeting'
    data       TEXT,
    created_at TEXT,
    UNIQUE(src_id, dst_id, relation)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(
    db_path: str | os.PathLike[str] | None = None,
    user_id: str | int | None = None,
) -> sqlite3.Connection:
    """Open (creating if needed) the brain database and ensure the schema exists.

    Isolation between users is a separate SQLite file per user, not a shared table with a
    user_id column — a missed WHERE-clause on any of the ~20 call sites across this codebase
    would leak one user's mail into another's LLM prompt, whereas a wrong file path just fails
    to find data. Precedence: an explicit `db_path` always wins (tests, the legacy CLI);
    otherwise `user_id` resolves to that user's own file; otherwise fall back to the
    pre-existing global `BRAIN_DB`/`DEFAULT_DB` behavior (the "legacy" bucket — no real user's
    data lives there once multi-user isolation is in place).
    """
    if db_path is not None:
        path = Path(db_path)
    elif user_id is not None:
        # BRAIN_DATA_DIR relocates the whole per-user tree. The end-to-end suite sets it so a
        # test run cannot touch (or wipe) a real user's mail: user ids collide across the dev
        # and test console databases, but the data directories no longer do.
        base = Path(os.environ.get("BRAIN_DATA_DIR") or (Path(__file__).resolve().parent / "data"))
        path = base / "users" / str(user_id) / "brain.db"
    else:
        path = Path(os.environ.get("BRAIN_DB") or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False because FastAPI runs sync dependencies (and their generator
    # cleanup) on threadpool workers, which are not guaranteed to be the thread that opened the
    # connection — without this, closing a request-scoped connection raises ProgrammingError.
    # Each request still gets its own connection, so no connection is shared concurrently.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _row_to_entity(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["data"] = json.loads(d.get("data") or "{}")
    return d


def _existing_for_resolver(conn: sqlite3.Connection, type_: str) -> list[dict[str, Any]]:
    """Load confirmed nodes of one type as the flat dicts the resolver expects (name/assignee/id)."""
    rows = conn.execute(
        "SELECT id, data FROM entities WHERE type = ? AND needs_review = 0", (type_,)
    ).fetchall()
    existing = []
    for r in rows:
        payload = json.loads(r["data"] or "{}")
        payload["id"] = r["id"]
        existing.append(payload)
    return existing


def upsert(
    conn: sqlite3.Connection,
    type_: str,
    candidate: dict[str, Any],
    *,
    title: str | None,
    summary: str | None,
    source: str | None,
    needs_review: bool | None = None,
) -> tuple[Resolution, str]:
    """Resolve `candidate` against existing nodes of `type_` and apply the decision idempotently.

    `candidate` must carry the resolver keys ("name", "assignee", optional source id) plus whatever
    payload you want stored. Returns (Resolution, entity_id).

    `needs_review` lets a caller set the flag explicitly rather than inheriting the resolver's
    verdict — the mail pipeline uses it to mark a low-confidence category guess (see
    mail_ingest.arbitrate_category). It applies to the UPDATE path too, so a later confident
    email can *clear* a flag an earlier ambiguous one raised.
    """
    res = resolve(candidate, _existing_for_resolver(conn, type_))
    payload = json.dumps(candidate, ensure_ascii=False)
    now = _now()

    if res.action == "update" and res.matched_id:
        if needs_review is None:
            conn.execute(
                "UPDATE entities SET title=?, summary=?, data=?, source=?, updated_at=? WHERE id=?",
                (title, summary, payload, source, now, res.matched_id),
            )
        else:
            conn.execute(
                "UPDATE entities SET title=?, summary=?, data=?, source=?, needs_review=?, "
                "updated_at=? WHERE id=?",
                (title, summary, payload, source, int(needs_review), now, res.matched_id),
            )
        conn.commit()
        return res, res.matched_id

    # create, or review (stored but flagged so a human confirms — never silently merged)
    flag = int(needs_review) if needs_review is not None else int(res.action == "review")
    # COALESCE keeps the original created_at: a flagged row is invisible to
    # _existing_for_resolver (it filters needs_review = 0), so the resolver says "create" for a
    # row that already exists and this INSERT OR REPLACE would otherwise reset its birth date.
    conn.execute(
        "INSERT OR REPLACE INTO entities "
        "(id, type, natural_key, title, summary, data, source, needs_review, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, "
        "COALESCE((SELECT created_at FROM entities WHERE id = ?), ?), ?)",
        (res.key, type_, res.key, title, summary, payload, source, flag, res.key, now, now),
    )
    conn.commit()
    return res, res.key


def add_edge(
    conn: sqlite3.Connection,
    src_id: str,
    dst_id: str,
    relation: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Add a typed directed edge (idempotent on src+dst+relation)."""
    conn.execute(
        "INSERT OR IGNORE INTO edges (src_id, dst_id, relation, data, created_at) VALUES (?, ?, ?, ?, ?)",
        (src_id, dst_id, relation, json.dumps(data) if data else None, _now()),
    )
    conn.commit()


def all_of_type(conn: sqlite3.Connection, type_: str) -> list[dict[str, Any]]:
    """Every node of a type, newest first, with `data` parsed."""
    rows = conn.execute(
        "SELECT * FROM entities WHERE type = ? ORDER BY updated_at DESC", (type_,)
    ).fetchall()
    return [_row_to_entity(r) for r in rows]


def get(conn: sqlite3.Connection, entity_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    return _row_to_entity(row) if row else None


def neighbors(
    conn: sqlite3.Connection, entity_id: str, relation: str | None = None, *, incoming: bool = False
) -> list[dict[str, Any]]:
    """Nodes reachable from (or pointing at) `entity_id`, optionally filtered by relation."""
    col, other = ("dst_id", "src_id") if incoming else ("src_id", "dst_id")
    sql = f"SELECT {other} AS oid FROM edges WHERE {col} = ?"
    params: list[Any] = [entity_id]
    if relation:
        sql += " AND relation = ?"
        params.append(relation)
    ids = [r["oid"] for r in conn.execute(sql, params).fetchall()]
    return [e for e in (get(conn, i) for i in ids) if e]


def delete(conn: sqlite3.Connection, entity_id: str) -> bool:
    """Delete one node and every edge touching it. Returns whether the node existed."""
    cur = conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
    conn.execute("DELETE FROM edges WHERE src_id = ? OR dst_id = ?", (entity_id, entity_id))
    conn.commit()
    return cur.rowcount > 0
