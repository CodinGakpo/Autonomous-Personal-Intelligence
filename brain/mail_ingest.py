"""brain/mail_ingest.py — the mail knowledge-tree pipeline.

    list ─▶ attachments ─▶ classify (LLM) ─▶ merge (LLM) ─▶ store ─▶ mark-read

Builds three new node types in the existing brain (brain/store.py's entities/edges):

    mail_category ──contains──▶ mail_topic ──contains──▶ mail_thread

Plain Python, no Hermes — run manually or from a scheduled task. See
docs/superpowers/specs/2026-08-30-mail-knowledge-tree-design.md for the design.

Usage:
    uv run python -m brain.mail_ingest run
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from brain import store
from brain.mail_attachments import process_attachment
from brain.openrouter import call_openrouter

CONFIG_PATH = Path(__file__).resolve().parent / "mail_config.json"

DEFAULT_CONFIG = {
    "student_id": "",
    "resume_path": "",
    "seeded_categories": ["Lectures & Profs", "Placements", "General College"],
}


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Read brain/mail_config.json (copy brain/mail_config.example.json to get started),
    filling in defaults for anything missing."""
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    data = json.loads(path.read_text(encoding="utf-8"))
    return {**DEFAULT_CONFIG, **data}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "untitled"


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def classify_email(
    email: dict[str, Any],
    attachment_findings: list[dict[str, Any]],
    categories: list[dict[str, Any]],
) -> dict[str, Any]:
    """LLM call: which category + topic does this email belong to (existing or new)?"""
    cat_lines = (
        "\n".join(
            f"- {c['title']}: {c.get('summary', '')}" for c in categories
        )
        or "(none yet)"
    )
    findings_text = (
        "\n".join(
            f"- {f['file']} ({f['kind']}): {f['finding']}"
            for f in attachment_findings
        )
        or "(none)"
    )
    prompt = (
        "You file one email into a knowledge tree. Pick the best-fitting CATEGORY "
        "(a broad area) and, within it, the best-fitting TOPIC (a specific thing, "
        "e.g. a company name or account). Prefer an existing category/topic; only "
        "propose a new one when nothing existing fits.\n\n"
        f"EXISTING CATEGORIES:\n{cat_lines}\n\n"
        f"EMAIL\nFrom: {email.get('from')}\nSubject: {email.get('subject')}\n"
        f"Body: {email.get('body_text', '')[:2000]}\n"
        f"Attachment findings:\n{findings_text}\n\n"
        "Reply with ONLY this JSON object, nothing else:\n"
        '{"category": "<name>", "new_category": true|false, "topic": "<name>", '
        '"new_topic": true|false}'
    )
    raw = _strip_fences(call_openrouter(prompt))
    return json.loads(raw)


def merge_or_create_thread(
    email: dict[str, Any],
    attachment_findings: list[dict[str, Any]],
    existing_threads: list[dict[str, Any]],
) -> dict[str, Any]:
    """LLM call: merge into an existing thread node, or create a new one."""
    thread_lines = (
        "\n".join(
            f"- id={t['id']}: {t.get('summary', '')}" for t in existing_threads
        )
        or "(none yet)"
    )
    findings_text = (
        "\n".join(
            f"- {f['file']} ({f['kind']}): {f['finding']}"
            for f in attachment_findings
        )
        or "(none)"
    )
    prompt = (
        "You maintain a knowledge node for one topic. Given a new email and the "
        "topic's existing nodes (id + summary), decide whether this email is "
        "closely related enough to merge into one of them (e.g. another round of "
        "the same process: interview, PPT, OA, result) or is unrelated enough to "
        "start a new node.\n\n"
        "If merging, write an updated body that folds the new information into "
        "the existing one coherently (a running picture, not a raw concatenation) "
        "and a fresh short summary.\n"
        "If new, write a body and summary for just this email.\n\n"
        f"EXISTING NODES IN THIS TOPIC:\n{thread_lines}\n\n"
        f"NEW EMAIL\nFrom: {email.get('from')}\nSubject: {email.get('subject')}\n"
        f"Body: {email.get('body_text', '')[:2000]}\n"
        f"Attachment findings:\n{findings_text}\n\n"
        "Reply with ONLY this JSON object, nothing else:\n"
        '{"action": "merge"|"new", "merge_into_id": "<id or null>", '
        '"summary": "<routing digest, <=120 words>", "body": "<full content>"}'
    )
    raw = _strip_fences(call_openrouter(prompt))
    return json.loads(raw)


def gather_attachment_findings(
    email: dict[str, Any], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Process all attachments in an email and gather findings."""
    findings = []
    for att in email.get("attachments", []):
        saved_to = att.get("saved_to")
        if not saved_to:
            continue
        findings.append(process_attachment(Path(saved_to), config))
    return findings


def _reparent_thread(conn: Any, thread_id: str, new_topic_id: str) -> None:
    """Ensure a thread has exactly one 'contains' parent.

    Drops any stale incoming 'contains' edge from a different topic before the
    caller adds the new one.
    """
    conn.execute(
        "DELETE FROM edges WHERE dst_id = ? AND relation = 'contains' AND src_id != ?",
        (thread_id, new_topic_id),
    )
    conn.commit()


def ingest_email(
    conn: Any, email: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    """Full per-email pipeline: attachments -> classify -> merge/place -> store.

    No mark-read here.
    """
    findings = gather_attachment_findings(email, config)

    stored_categories = store.all_of_type(conn, "mail_category")
    seeded_names = {c["title"] for c in stored_categories}
    categories = stored_categories + [
        {"title": name, "summary": ""}
        for name in config.get("seeded_categories", [])
        if name not in seeded_names
    ]
    classification = classify_email(email, findings, categories)

    cat_title = classification["category"]
    cat_id = f"mail:cat:{_slugify(cat_title)}"
    store.upsert(
        conn,
        "mail_category",
        {"source_id": cat_id, "title": cat_title},
        title=cat_title,
        summary=f"Mail about {cat_title}.",
        source="mail",
    )

    topic_title = classification["topic"]
    topic_id = f"mail:topic:{_slugify(cat_title)}:{_slugify(topic_title)}"
    existing_topic = store.get(conn, topic_id)
    store.upsert(
        conn,
        "mail_topic",
        {"source_id": topic_id, "title": topic_title},
        title=topic_title,
        summary=(
            existing_topic["summary"]
            if existing_topic
            else f"Mail about {topic_title}."
        ),
        source="mail",
    )
    store.add_edge(conn, cat_id, topic_id, "contains")

    existing_threads = [
        t
        for t in store.all_of_type(conn, "mail_thread")
        if any(
            n["id"] == topic_id
            for n in store.neighbors(conn, t["id"], "contains", incoming=True)
        )
    ]
    decision = merge_or_create_thread(email, findings, existing_threads)

    # Validate against every real thread, not just this topic's existing_threads: a merge target
    # from a different topic is legitimate (reclassification), a fully hallucinated id is not.
    valid_thread_ids = {t["id"] for t in store.all_of_type(conn, "mail_thread")}
    if decision["action"] == "merge" and decision.get("merge_into_id") in valid_thread_ids:
        thread_id = decision["merge_into_id"]
        existing_thread = store.get(conn, thread_id)
        prior_uids = (
            existing_thread["data"].get("source_uids", [])
            if existing_thread
            else []
        )
        uids = sorted({*prior_uids, email["uid"]})
        title = existing_thread["title"] if existing_thread else email.get("subject", "")
        source = ",".join(f"mail:{u}" for u in uids)
    else:
        thread_id = f"mail:thread:{email['uid']}"
        uids = [email["uid"]]
        title = email.get("subject", "")
        source = f"mail:{email['uid']}"

    store.upsert(
        conn,
        "mail_thread",
        {
            "source_id": thread_id,
            "title": title,
            "body": decision["body"],
            "source_uids": uids,
        },
        title=title,
        summary=decision["summary"],
        source=source,
    )
    _reparent_thread(conn, thread_id, topic_id)
    store.add_edge(conn, topic_id, thread_id, "contains")

    return {
        "uid": email["uid"],
        "category": cat_title,
        "topic": topic_title,
        "thread_id": thread_id,
        "action": decision["action"],
    }


EMAILTOOL = Path(__file__).resolve().parent / "emailtool.py"


def fetch_unread_emails() -> list[dict[str, Any]]:
    """Run emailtool.py list; return the parsed unread-email list."""
    proc = subprocess.run(
        [sys.executable, str(EMAILTOOL), "list"],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    if proc.returncode != 0:
        raise SystemExit(f"emailtool.py list failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def mark_email_read(uid: str) -> None:
    """Run emailtool.py mark-read <uid>."""
    proc = subprocess.run(
        [sys.executable, str(EMAILTOOL), "mark-read", uid],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    if proc.returncode != 0:
        raise SystemExit(f"emailtool.py mark-read failed: {proc.stderr.strip()}")


def run(conn: Any = None) -> list[dict[str, Any]]:
    """Fetch unread mail, ingest each into the tree, mark read only on success."""
    conn = conn or store.connect()
    config = load_config()
    if config.get("resume_path"):
        from tools.resume.parser import parse_resume

        config["resume_profile"] = parse_resume(Path(config["resume_path"]))

    results = []
    for email in fetch_unread_emails():
        try:
            result = ingest_email(conn, email, config)
            mark_email_read(email["uid"])
        except (Exception, SystemExit) as exc:  # one bad email must not stop the whole run
            results.append({"uid": email.get("uid"), "error": str(exc)})
            continue
        results.append(result)
    return results


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] != "run":
        print("usage: python -m brain.mail_ingest run", file=sys.stderr)
        sys.exit(2)
    for result in run():
        if "error" in result:
            print(f"[error] uid {result['uid']}: {result['error']}")
        else:
            tid = result["thread_id"]
            print(
                f"[{result['action']}] {result['category']} / "
                f"{result['topic']} -> {tid}"
            )


if __name__ == "__main__":
    main()
