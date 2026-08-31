"""Tests for the mail knowledge-tree pipeline: config, and classify/merge LLM-call parsing."""

import json

from brain import mail_ingest, store


def test_load_config_defaults_when_missing(tmp_path):
    cfg = mail_ingest.load_config(tmp_path / "nope.json")
    assert cfg["seeded_categories"] == ["Lectures & Profs", "Placements", "General College"]
    assert cfg["student_id"] == ""


def test_load_config_merges_file_over_defaults(tmp_path):
    path = tmp_path / "mail_config.json"
    path.write_text(json.dumps({"student_id": "S1"}), encoding="utf-8")
    cfg = mail_ingest.load_config(path)
    assert cfg["student_id"] == "S1"
    assert cfg["seeded_categories"] == ["Lectures & Profs", "Placements", "General College"]


def test_slugify():
    assert mail_ingest._slugify("Acme Corp!") == "acme-corp"
    assert mail_ingest._slugify("") == "untitled"


_CATEGORY_KEYWORDS = {
    "Placements": ["placement", "internship", "accenture", "training", "registration"],
    "Academics": ["assignment", "submission", "exam", "faculty", "project", "phase"],
}


def test_guess_category_bm25_picks_the_clear_winner():
    text = "Fwd: Accenture Batch1 Training for 2027 Batch registration open"
    assert mail_ingest.guess_category_bm25(text, _CATEGORY_KEYWORDS) == "Placements"


def test_guess_category_bm25_picks_the_other_clear_winner():
    text = "BCSE332L Project Phase 4 submission instructions before the exam"
    assert mail_ingest.guess_category_bm25(text, _CATEGORY_KEYWORDS) == "Academics"


def test_guess_category_bm25_returns_none_when_no_keywords_match():
    assert mail_ingest.guess_category_bm25("Let's get lunch tomorrow", _CATEGORY_KEYWORDS) is None


def test_guess_category_bm25_returns_none_on_empty_config():
    assert mail_ingest.guess_category_bm25("Accenture training", {}) is None


def test_guess_category_bm25_returns_none_on_a_tie():
    tied = {"A": ["accenture"], "B": ["accenture"]}
    assert mail_ingest.guess_category_bm25("Accenture email", tied) is None


def test_classify_email_parses_llm_json(monkeypatch):
    reply = (
        '{"category": "Placements", "new_category": false, '
        '"topic": "Acme", "new_topic": true}'
    )
    monkeypatch.setattr(mail_ingest, "call_openrouter", lambda prompt: reply)
    result = mail_ingest.classify_email(
        {"from": "a@x.com", "subject": "Interview", "body_text": "..."}, [], [],
    )
    assert result == {
        "category": "Placements", "new_category": False, "topic": "Acme", "new_topic": True,
    }


def test_classify_email_strips_markdown_fences(monkeypatch):
    reply = (
        '```json\n{"category": "Placements", "new_category": false, '
        '"topic": "Acme", "new_topic": false}\n```'
    )
    monkeypatch.setattr(mail_ingest, "call_openrouter", lambda prompt: reply)
    result = mail_ingest.classify_email({"from": "a", "subject": "s", "body_text": "b"}, [], [])
    assert result["category"] == "Placements"


def test_merge_or_create_thread_parses_llm_json(monkeypatch):
    monkeypatch.setattr(
        mail_ingest, "call_openrouter",
        lambda prompt: '{"action": "new", "merge_into_id": null, "summary": "s", "body": "b"}',
    )
    result = mail_ingest.merge_or_create_thread(
        {"from": "a", "subject": "s", "body_text": "b"}, [], [],
    )
    assert result["action"] == "new"
    assert result["body"] == "b"


def _conn(tmp_path):
    return store.connect(tmp_path / "t.db")


def _email(uid="1", subject="Interview Round 1"):
    return {
        "uid": uid, "from": "hr@acme.com", "to": "me@x.com", "subject": subject,
        "body_text": "...", "attachments": [],
    }


def test_ingest_email_overrides_llm_category_with_confident_bm25_guess(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    email = _email(uid="9", subject="Accenture Batch1 Training registration")
    monkeypatch.setattr(
        mail_ingest, "classify_email",
        # LLM (wrongly) says Academics; the deterministic guess should override it to Placements.
        lambda email, findings, categories: {
            "category": "Academics", "new_category": True, "topic": "Accenture", "new_topic": True,
        },
    )
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "new", "merge_into_id": None, "summary": "s", "body": "b",
        },
    )
    config = {
        "student_id": "", "resume_path": "",
        "category_keywords": mail_ingest.DEFAULT_CONFIG["category_keywords"],
    }
    result = mail_ingest.ingest_email(conn, email, config)

    assert result["category"] == "Placements"
    assert store.get(conn, "mail:cat:placements") is not None
    assert store.get(conn, "mail:cat:academics") is None


def test_ingest_email_creates_category_topic_and_thread(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(
        mail_ingest, "classify_email",
        lambda email, findings, categories: {
            "category": "Placements", "new_category": True, "topic": "Acme", "new_topic": True,
        },
    )
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "new", "merge_into_id": None,
            "summary": "Interview scheduled.", "body": "Round 1 interview on Monday.",
        },
    )
    result = mail_ingest.ingest_email(conn, _email(), {"student_id": "", "resume_path": ""})

    assert result["category"] == "Placements"
    assert result["topic"] == "Acme"
    assert store.get(conn, "mail:cat:placements")["title"] == "Placements"
    assert store.get(conn, "mail:topic:placements:acme")["title"] == "Acme"
    thread = store.get(conn, result["thread_id"])
    assert thread["data"]["body"] == "Round 1 interview on Monday."
    assert thread["data"]["source_uids"] == ["1"]


def test_ingest_email_merges_second_related_email_into_same_thread(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(
        mail_ingest, "classify_email",
        lambda email, findings, categories: {
            "category": "Placements", "new_category": True, "topic": "Acme", "new_topic": True,
        },
    )
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "new", "merge_into_id": None,
            "summary": "Interview scheduled.", "body": "Round 1 interview.",
        },
    )
    first = mail_ingest.ingest_email(conn, _email(uid="1"), {"student_id": "", "resume_path": ""})

    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "merge", "merge_into_id": first["thread_id"],
            "summary": "Interview + PPT scheduled.",
            "body": "Round 1 interview.\nPPT on Wednesday.",
        },
    )
    second_email = _email(uid="2", subject="PPT")
    second = mail_ingest.ingest_email(conn, second_email, {"student_id": "", "resume_path": ""})

    assert second["thread_id"] == first["thread_id"]
    thread = store.get(conn, second["thread_id"])
    assert thread["data"]["body"] == "Round 1 interview.\nPPT on Wednesday."
    assert sorted(thread["data"]["source_uids"]) == ["1", "2"]
    assert len(store.all_of_type(conn, "mail_thread")) == 1


def test_run_marks_read_only_on_success(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    monkeypatch.setattr(
        mail_ingest, "fetch_unread_emails",
        lambda since_minutes=None: [_email(uid="1"), _email(uid="2", subject="bad")],
    )

    def fake_ingest(conn_, email, config):
        if email["uid"] == "2":
            raise ValueError("boom")
        return {
            "uid": email["uid"], "category": "C", "topic": "T",
            "thread_id": "mail:thread:1", "action": "new",
        }

    monkeypatch.setattr(mail_ingest, "ingest_email", fake_ingest)
    marked = []
    monkeypatch.setattr(mail_ingest, "mark_email_read", lambda uid: marked.append(uid))
    monkeypatch.setattr(mail_ingest, "load_config", lambda: {"student_id": "", "resume_path": ""})

    results = mail_ingest.run(conn)

    assert marked == ["1"]
    assert results[0]["uid"] == "1"
    assert results[1]["error"] == "boom"


def test_run_marks_read_failure_does_not_abort_batch(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    monkeypatch.setattr(
        mail_ingest, "fetch_unread_emails",
        lambda since_minutes=None: [_email(uid="1"), _email(uid="2", subject="second")],
    )

    def fake_ingest(conn_, email, config):
        return {
            "uid": email["uid"], "category": "C", "topic": "T",
            "thread_id": f"mail:thread:{email['uid']}", "action": "new",
        }

    def fake_mark_read(uid):
        if uid == "1":
            raise SystemExit("emailtool.py mark-read failed: boom")

    monkeypatch.setattr(mail_ingest, "ingest_email", fake_ingest)
    monkeypatch.setattr(mail_ingest, "mark_email_read", fake_mark_read)
    monkeypatch.setattr(mail_ingest, "load_config", lambda: {"student_id": "", "resume_path": ""})

    results = mail_ingest.run(conn)

    assert results[0]["uid"] == "1"
    assert "error" in results[0]
    assert results[1]["uid"] == "2"
    assert "error" not in results[1]


def test_ingest_email_ignores_hallucinated_merge_into_id(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(
        mail_ingest, "classify_email",
        lambda email, findings, categories: {
            "category": "Placements", "new_category": True, "topic": "Acme", "new_topic": True,
        },
    )
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "merge", "merge_into_id": "mail:thread:does-not-exist",
            "summary": "s", "body": "b",
        },
    )
    result = mail_ingest.ingest_email(conn, _email(uid="1"), {"student_id": "", "resume_path": ""})

    assert result["thread_id"] == "mail:thread:1"
    thread = store.get(conn, "mail:thread:1")
    assert thread is not None
    assert store.get(conn, "mail:thread:does-not-exist") is None


def test_ingest_email_reclassified_thread_has_single_parent(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(
        mail_ingest, "classify_email",
        lambda email, findings, categories: {
            "category": "Placements", "new_category": True, "topic": "Acme", "new_topic": True,
        },
    )
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "new", "merge_into_id": None,
            "summary": "s1", "body": "Round 1 interview.",
        },
    )
    first = mail_ingest.ingest_email(conn, _email(uid="1"), {"student_id": "", "resume_path": ""})
    thread_id = first["thread_id"]

    monkeypatch.setattr(
        mail_ingest, "classify_email",
        lambda email, findings, categories: {
            "category": "Placements", "new_category": False, "topic": "Beta", "new_topic": True,
        },
    )
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "merge", "merge_into_id": thread_id,
            "summary": "s2", "body": "Reclassified into Beta.",
        },
    )
    reclassified_email = _email(uid="2", subject="PPT")
    mail_ingest.ingest_email(conn, reclassified_email, {"student_id": "", "resume_path": ""})

    parents = store.neighbors(conn, thread_id, "contains", incoming=True)
    assert len(parents) == 1
    assert parents[0]["title"] == "Beta"


def test_ingest_email_includes_seeded_categories_not_yet_stored(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    captured = {}

    def fake_classify(email, findings, categories):
        captured["categories"] = categories
        return {"category": "Placements", "new_category": True, "topic": "Acme", "new_topic": True}

    monkeypatch.setattr(mail_ingest, "classify_email", fake_classify)
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "new", "merge_into_id": None, "summary": "s", "body": "b",
        },
    )
    mail_ingest.ingest_email(
        conn, _email(uid="1"),
        {"student_id": "", "resume_path": "", "seeded_categories": ["Placements", "Banking"]},
    )

    titles = {c["title"] for c in captured["categories"]}
    assert "Placements" in titles
    assert "Banking" in titles


def test_ingest_email_merge_preserves_title_and_accumulates_source(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(
        mail_ingest, "classify_email",
        lambda email, findings, categories: {
            "category": "Placements", "new_category": True, "topic": "Acme", "new_topic": True,
        },
    )
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "new", "merge_into_id": None,
            "summary": "s1", "body": "Round 1 interview.",
        },
    )
    first = mail_ingest.ingest_email(conn, _email(uid="1", subject="Round 1"), {})

    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "merge", "merge_into_id": first["thread_id"],
            "summary": "s2", "body": "Round 1 interview.\nPPT on Wednesday.",
        },
    )
    mail_ingest.ingest_email(conn, _email(uid="2", subject="PPT"), {})

    thread = store.get(conn, first["thread_id"])
    assert thread["title"] == "Round 1"
    assert thread["source"] == "mail:1,mail:2"
