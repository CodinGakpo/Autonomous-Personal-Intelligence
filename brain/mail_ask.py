"""brain/mail_ask.py — answer natural-language questions over the ingested mail tree.

Mirrors brain/ask.py's Navigate -> Think shape but for mail_category -> mail_topic ->
mail_thread nodes, and rides brain.openrouter (not brain.engine) since that's the engine
already proven for the mail pipeline (classification/summarization in mail_ingest.py).

Retrieval is bounded, not "dump the mailbox": every thread gets one summary line in the
prompt (cheap — titles/summaries are short even at hundreds of threads), but only the BM25
top-K threads against the question get their full body text included, so prompt size stays
roughly constant as the mailbox grows. Plain-text answer, no citation contract — matches the
MailChat UI, which has no "sources" affordance today.
"""

from __future__ import annotations

from typing import Any

from brain import bm25, profile, store
from brain.openrouter import call_openrouter

TOP_K = 8  # tunable: how many full thread bodies to include, see module docstring

SYSTEM = """You are a mail assistant answering questions about someone's inbox, using a
knowledge tree built from their ingested email (organized as category > topic > thread).
Answer ONLY from the MAIL CONTEXT below — never invent senders, dates, deadlines, or facts
that aren't there. If the answer isn't in the context, say plainly that you don't see it in
the ingested mail rather than guessing. Keep answers short and direct (a sentence or two,
longer only if the question needs a list). Do not mention internal details like "BM25",
"top threads", or how this context was assembled — just answer the question.

Attachment findings are authoritative. They come from actually reading the file, whereas a
thread's summary is prose written earlier and may be out of date — where the two disagree
about whether an attachment mentions the user, trust the attachment finding."""


def _walk_tree(conn: Any) -> list[tuple[str, str, dict[str, Any]]]:
    """Flatten mail_category -> mail_topic -> mail_thread into (category_title, topic_title,
    thread_entity) tuples — same traversal shape as viz_server's _mail_children/_mail_node."""
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for cat in store.all_of_type(conn, "mail_category"):
        for topic in store.neighbors(conn, cat["id"], "contains"):
            if topic["type"] != "mail_topic":
                continue
            for thread in store.neighbors(conn, topic["id"], "contains"):
                if thread["type"] != "mail_thread":
                    continue
                rows.append((cat["title"], topic["title"], thread))
    return rows


def _thread_doc_text(thread: dict[str, Any]) -> str:
    body = (thread.get("data") or {}).get("body") or ""
    # Attachment text is part of what a thread "says": a shortlist spreadsheet may be the only
    # place a company name or your roll number appears, so it must be rankable too.
    attachments = " ".join(
        " ".join(
            [
                str(f.get("file") or ""),
                str(f.get("finding") or ""),
                *(str(m) for m in (f.get("mentions_you") or [])),
            ]
        )
        for f in ((thread.get("data") or {}).get("attachments") or [])
        if isinstance(f, dict)
    )
    parts = (thread.get("title"), thread.get("summary"), body, attachments)
    return " ".join(str(p) for p in parts if p)


def _rank_threads(
    question: str,
    rows: list[tuple[str, str, dict[str, Any]]],
    *,
    top_k: int = TOP_K,
) -> list[tuple[str, str, dict[str, Any]]]:
    """BM25-rank every thread against `question`; return the top_k with score > 0, in order.

    A thread that shares no terms with the question is never expanded to full body — the
    one-line overview is enough for the model to (correctly) say it isn't there.
    """
    if not rows:
        return []
    documents = {thread["id"]: _thread_doc_text(thread) for _, _, thread in rows}
    ranked = bm25.rank(question, documents)
    by_id = {thread["id"]: (cat, topic, thread) for cat, topic, thread in rows}
    top_ids = [tid for tid, score in ranked if score > 0][:top_k]
    return [by_id[tid] for tid in top_ids]


def _overview_attachment_note(thread: dict[str, Any]) -> str:
    """A compact attachment marker for the one-line overview.

    "Is my name in any attachment?" is a question about *every* thread, but only the top few
    are expanded in full — so the answer has to be visible from the overview alone.
    """
    findings = [
        f for f in ((thread.get("data") or {}).get("attachments") or []) if isinstance(f, dict)
    ]
    if not findings:
        return ""
    named = sorted({m for f in findings for m in (f.get("mentions_you") or [])})
    if named:
        return f" [{len(findings)} attachment(s); NAMES THE USER: {', '.join(map(str, named))}]"
    return f" [{len(findings)} attachment(s); does not name the user]"


def _format_overview(rows: list[tuple[str, str, dict[str, Any]]]) -> str:
    lines = []
    for cat, topic, thread in rows:
        summary = thread.get("summary") or "(no summary)"
        # The attachment verdict leads the line. Appended to the end it landed ~525 characters
        # in, after a long summary, and a small model simply did not attend to it — it answered
        # "not listed" about a shortlist the line said named the user.
        note = _overview_attachment_note(thread)
        prefix = f"{note} " if note else ""
        lines.append(f"  {prefix}[{cat} > {topic}] {thread['title']} — {summary}")
    return "\n".join(lines)


def _format_attachments(thread: dict[str, Any]) -> str:
    """What was found inside this thread's attachments, including whether it named the user.

    Without this the answer side is blind to attachments entirely: findings are produced at
    ingest and would otherwise never reach the question being asked.
    """
    findings = (thread.get("data") or {}).get("attachments") or []
    if not findings:
        return ""
    lines = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        name = finding.get("file", "attachment")
        kind = finding.get("kind", "file")
        mentions = finding.get("mentions_you") or []
        marker = f" [NAMES THE USER: {', '.join(map(str, mentions))}]" if mentions else ""
        detail = finding.get("finding")
        lines.append(f"- {name} ({kind}){marker}: {detail}")
    return "\nAttachments:\n" + "\n".join(lines) if lines else ""


def _format_full_thread(cat: str, topic: str, thread: dict[str, Any]) -> str:
    body = (thread.get("data") or {}).get("body") or "(no body captured)"
    # Attachments precede the prose. A summary is written by the model at ingest and can go
    # stale — one here read "attachments indicate the sender was not listed" for a spreadsheet
    # that does name the user — so the scanned facts must be read first, not last.
    return (
        f"### {thread['title']}  [{cat} > {topic}]"
        f"{_format_attachments(thread)}\n"
        f"Summary: {thread.get('summary') or '(none)'}\n"
        f"Body:\n{body}"
    )


def _format_profile(profile_details: list[dict[str, str]]) -> str:
    lines = [f"  {d.get('key', '')}: {d.get('value', '')}" for d in profile_details if d.get("key")]
    return "\n".join(lines) if lines else "(none provided)"


def build_prompt(
    question: str,
    rows: list[tuple[str, str, dict[str, Any]]],
    top_threads: list[tuple[str, str, dict[str, Any]]],
    profile_details: list[dict[str, str]],
) -> str:
    overview = _format_overview(rows)
    full = "\n\n".join(_format_full_thread(c, t, th) for c, t, th in top_threads) or (
        "(no thread matched this question closely — rely on the overview above, and say so "
        "if it isn't enough to answer)"
    )
    # Not named `profile`: that would shadow the imported brain.profile module.
    profile_block = _format_profile(profile_details)
    return (
        f"{SYSTEM}\n\n"
        f"=== MAIL OVERVIEW (every thread, one line each) ===\n{overview}\n\n"
        f"=== RELEVANT THREADS IN FULL ===\n{full}\n\n"
        f"=== ABOUT THE PERSON ASKING (optional context) ===\n{profile_block}\n\n"
        f"=== QUESTION ===\n{question}\n"
    )


def ask_mail(
    conn: Any,
    question: str,
    profile_details: list[dict[str, str]] | None = None,
    *,
    top_k: int = TOP_K,
) -> dict[str, str]:
    """Answer `question` over the mail knowledge tree. Returns {"answer": str}.

    Empty tree short-circuits to a canned message without calling the LLM (mirrors
    brain.ask.ask's empty-catalogue return).
    """
    rows = _walk_tree(conn)
    if not rows:
        return {
            "answer": "Your mail knowledge tree is empty — connect your mailbox and let it "
            "ingest some mail first, then ask again."
        }
    # The profile lives server-side (brain/profile.py) so headless ingestion can read it too;
    # anything the caller passes is merged on top rather than replacing it.
    stored = profile.load_profile(conn)
    seen = {d.get("key", "").strip().lower() for d in (profile_details or [])}
    merged = list(profile_details or []) + [d for d in stored if d["key"].lower() not in seen]

    top_threads = _rank_threads(question, rows, top_k=top_k)
    prompt = build_prompt(question, rows, top_threads, merged)
    reply = call_openrouter(prompt)
    return {"answer": reply.strip()}
