"""Tests for brain/mail_ask.py — mail-tree Q&A retrieval + prompting."""

from brain import mail_ask, store


def _conn(tmp_path):
    return store.connect(tmp_path / "t.db")


def _seed_thread(conn, cat_title, topic_title, thread_id, title, summary, body):
    cat_id = f"mail:cat:{cat_title.lower()}"
    topic_id = f"mail:topic:{cat_title.lower()}:{topic_title.lower()}"
    store.upsert(
        conn, "mail_category", {"source_id": cat_id, "title": cat_title},
        title=cat_title, summary=f"Mail about {cat_title}.", source="mail",
    )
    store.upsert(
        conn, "mail_topic", {"source_id": topic_id, "title": topic_title},
        title=topic_title, summary=f"Mail about {topic_title}.", source="mail",
    )
    store.upsert(
        conn, "mail_thread",
        {"source_id": thread_id, "title": title, "body": body, "source_uids": ["1"]},
        title=title, summary=summary, source="mail:1",
    )
    store.add_edge(conn, cat_id, topic_id, "contains")
    store.add_edge(conn, topic_id, thread_id, "contains")


def test_ask_mail_empty_tree_returns_canned_message_without_calling_llm(tmp_path, monkeypatch):
    conn = _conn(tmp_path)

    def boom(prompt):
        raise AssertionError("should not call the LLM on an empty tree")

    monkeypatch.setattr(mail_ask, "call_openrouter", boom)
    result = mail_ask.ask_mail(conn, "anything?")
    assert "empty" in result["answer"].lower()


def test_ask_mail_includes_matching_thread_body_in_prompt(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    _seed_thread(
        conn, "Placements", "Acme", "mail:thread:1",
        "Interview Round 1", "Interview scheduled Monday.",
        "Please join the interview call on Monday at 10am.",
    )
    _seed_thread(
        conn, "Lectures", "DBMS", "mail:thread:2",
        "Assignment 2", "Assignment due Friday.",
        "Submit assignment 2 by Friday via the portal.",
    )
    captured = {}

    def fake_call(prompt):
        captured["prompt"] = prompt
        return "You have an interview Monday at 10am."

    monkeypatch.setattr(mail_ask, "call_openrouter", fake_call)

    result = mail_ask.ask_mail(conn, "When is my Acme interview?")

    assert "interview call on Monday" in captured["prompt"]  # top match expanded in full
    assert "Assignment 2" in captured["prompt"]  # unrelated thread still in overview
    assert "Submit assignment 2 by Friday via the portal." not in captured["prompt"]  # not expanded
    assert result["answer"] == "You have an interview Monday at 10am."


def test_ask_mail_respects_top_k(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    for i in range(12):
        _seed_thread(
            conn, "Placements", "Acme", f"mail:thread:{i}",
            f"Interview Round {i}", "Interview scheduled.",
            "interview interview interview call scheduled",
        )
    captured = {}
    monkeypatch.setattr(
        mail_ask, "call_openrouter", lambda p: captured.setdefault("prompt", p) or "ok"
    )
    mail_ask.ask_mail(conn, "interview call", top_k=3)
    assert captured["prompt"].count("### ") == 3


def test_ask_mail_folds_profile_details_into_prompt(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    _seed_thread(conn, "Placements", "Acme", "mail:thread:1", "Interview", "s", "interview body")
    captured = {}
    monkeypatch.setattr(
        mail_ask, "call_openrouter", lambda p: captured.setdefault("prompt", p) or "ok"
    )
    mail_ask.ask_mail(conn, "interview", [{"key": "Timezone", "value": "IST"}])
    assert "Timezone: IST" in captured["prompt"]
