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

from brain import bm25, store
from brain.openrouter import call_openrouter

TOP_K = 8  # tunable: how many full thread bodies to include, see module docstring

SYSTEM = """You are a mail assistant answering questions about someone's inbox, using a
knowledge tree built from their ingested email (organized as category > topic > thread).
Answer ONLY from the MAIL CONTEXT below — never invent senders, dates, deadlines, or facts
that aren't there. If the answer isn't in the context, say plainly that you don't see it in
the ingested mail rather than guessing. Keep answers short and direct (a sentence or two,
longer only if the question needs a list). Do not mention internal details like "BM25",
"top threads", or how this context was assembled — just answer the question."""


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
    return " ".join(p for p in (thread.get("title"), thread.get("summary"), body) if p)


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


def _format_overview(rows: list[tuple[str, str, dict[str, Any]]]) -> str:
    lines = []
    for cat, topic, thread in rows:
        summary = thread.get("summary") or "(no summary)"
        lines.append(f"  [{cat} > {topic}] {thread['title']} — {summary}")
    return "\n".join(lines)


def _format_full_thread(cat: str, topic: str, thread: dict[str, Any]) -> str:
    body = (thread.get("data") or {}).get("body") or "(no body captured)"
    return (
        f"### {thread['title']}  [{cat} > {topic}]\n"
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
    profile = _format_profile(profile_details)
    return (
        f"{SYSTEM}\n\n"
        f"=== MAIL OVERVIEW (every thread, one line each) ===\n{overview}\n\n"
        f"=== RELEVANT THREADS IN FULL ===\n{full}\n\n"
        f"=== ABOUT THE PERSON ASKING (optional context) ===\n{profile}\n\n"
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
    top_threads = _rank_threads(question, rows, top_k=top_k)
    prompt = build_prompt(question, rows, top_threads, profile_details or [])
    reply = call_openrouter(prompt)
    return {"answer": reply.strip()}
