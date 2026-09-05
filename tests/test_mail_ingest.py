"""Tests for the mail knowledge-tree pipeline: config, and classify/merge LLM-call parsing."""

import json

from brain import mail_ingest, store
from brain import profile as brain_profile


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
    # "registration" is a stopword (it appears in placement, lecture and event mail alike), so
    # the winner has to stand on genuinely discriminative terms: accenture + training + internship.
    text = "Fwd: Accenture Batch1 Training for the 2027 Batch internship, registration open"
    assert mail_ingest.guess_category_bm25(text, _CATEGORY_KEYWORDS) == "Placements"


def test_guess_category_bm25_picks_the_other_clear_winner():
    text = "BCSE332L Project Phase 4 submission instructions before the exam"
    assert mail_ingest.guess_category_bm25(text, _CATEGORY_KEYWORDS) == "Academics"


def test_guess_category_bm25_returns_none_when_no_keywords_match():
    assert mail_ingest.guess_category_bm25("Let's get lunch tomorrow", _CATEGORY_KEYWORDS) is None


def test_guess_category_bm25_returns_none_on_empty_config():
    assert mail_ingest.guess_category_bm25("Accenture training", {}) is None


def test_guess_category_bm25_returns_none_on_a_tie():
    # Three hits each, so both clear the absolute floor and it is genuinely the *margin* that
    # rejects them — otherwise this test would pass for the wrong reason.
    tied = {
        "A": ["accenture", "interview", "offer letter"],
        "B": ["accenture", "interview", "offer letter"],
    }
    assert mail_ingest.guess_category_bm25("Accenture interview offer letter", tied) is None


def test_guess_category_bm25_returns_none_below_the_absolute_floor():
    assert mail_ingest.guess_category_bm25("Accenture email", {"A": ["accenture"]}) is None


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


def _defaults():
    """DEFAULT_CONFIG's classification keys, as ingest_email receives them in production."""
    return {
        "student_id": "",
        "resume_path": "",
        **{
            key: mail_ingest.DEFAULT_CONFIG[key]
            for key in ("category_keywords", "category_negative_keywords", "conditional_keywords")
        },
    }


def _fake_llm(monkeypatch, category, topic="Some Topic"):
    monkeypatch.setattr(
        mail_ingest, "classify_email",
        lambda email, findings, categories: {
            "category": category, "new_category": True, "topic": topic, "new_topic": True,
        },
    )
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "new", "merge_into_id": None, "summary": "s", "body": "b",
        },
    )


# The email that started this: a college yoga competition filed under Placements because the
# Training & Placement Cell organised it, it linked a Google Form, and the word "on" appeared.
_YOGA_EMAIL = {
    "uid": "77",
    "from": "tpcell@college.edu",
    "to": "me@x.com",
    "subject": "Yoga Competition 2026",
    "body_text": (
        "The Training and Placement Cell is organising a Yoga Competition on 12 March 2026. "
        "Register via the Google Form link below. All students of all years are welcome."
    ),
    "attachments": [],
}


def test_ingest_email_overrides_llm_category_with_confident_bm25_guess(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    email = _email(uid="9", subject="Accenture Off-Campus Drive - interview shortlisted")
    # LLM (wrongly) says Academics; the deterministic guess should override it to Placements.
    _fake_llm(monkeypatch, "Academics", topic="Accenture")
    result = mail_ingest.ingest_email(conn, email, _defaults())

    assert result["category"] == "Placements"
    assert result["confidence"] == "medium"  # confident keywords, disagreeing LLM
    assert store.get(conn, "mail:cat:placements") is not None
    assert store.get(conn, "mail:cat:academics") is None
    assert store.get(conn, result["thread_id"])["needs_review"] == 0


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
        lambda since_minutes=None, user_id=None: [_email(uid="1"), _email(uid="2", subject="bad")],
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
    monkeypatch.setattr(
        mail_ingest, "mark_email_read", lambda uid, user_id=None: marked.append(uid)
    )
    monkeypatch.setattr(mail_ingest, "load_config", lambda: {"student_id": "", "resume_path": ""})

    results = mail_ingest.run(conn)

    assert marked == ["1"]
    assert results[0]["uid"] == "1"
    assert results[1]["error"] == "boom"


def test_run_marks_read_failure_does_not_abort_batch(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    monkeypatch.setattr(
        mail_ingest, "fetch_unread_emails",
        lambda since_minutes=None, user_id=None: [
            _email(uid="1"), _email(uid="2", subject="second"),
        ],
    )

    def fake_ingest(conn_, email, config):
        return {
            "uid": email["uid"], "category": "C", "topic": "T",
            "thread_id": f"mail:thread:{email['uid']}", "action": "new",
        }

    def fake_mark_read(uid, user_id=None):
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


# --- Category scoring -------------------------------------------------------------------


def test_score_categories_weights_the_subject_above_the_body():
    cfg = {"category_keywords": {"P": ["internship"]}}
    assert dict(mail_ingest.score_categories("internship", "", "", cfg))["P"] == 3.0
    assert dict(mail_ingest.score_categories("", "internship", "", cfg))["P"] == 1.0
    assert dict(mail_ingest.score_categories("internship", "internship", "", cfg))["P"] == 4.0


def test_score_categories_counts_a_keyword_once_per_zone():
    cfg = {"category_keywords": {"P": ["internship"]}}
    assert dict(mail_ingest.score_categories("", "internship " * 5, "", cfg))["P"] == 1.0


def test_score_categories_matches_multiword_keywords_as_phrases():
    cfg = {"category_keywords": {"P": ["off-campus"]}}
    assert dict(mail_ingest.score_categories("Off-Campus Drive", "", "", cfg))["P"] == 3.0
    # The exact false positive that poisoned the old scorer: "on"/"off" as loose unigrams.
    loose = mail_ingest.score_categories("the drive is on and off again", "", "", cfg)
    assert dict(loose)["P"] == 0.0


def test_score_categories_ignores_stopword_only_keywords():
    cfg = {"category_keywords": {"P": ["on", "off", "company", "dream", "registration"]}}
    text = "the company on offer is a dream, registration open"
    assert dict(mail_ingest.score_categories(text, text, "", cfg))["P"] == 0.0


def test_score_categories_brand_keyword_needs_placement_context():
    cfg = {
        "category_keywords": {"P": ["google"]},
        "conditional_keywords": mail_ingest.DEFAULT_CONFIG["conditional_keywords"],
    }
    plain = mail_ingest.score_categories("", "register via the Google Form", "", cfg)
    assert dict(plain)["P"] == 0.0
    real = mail_ingest.score_categories("", "Google on-campus drive, shortlisted", "", cfg)
    assert dict(real)["P"] > 0


def test_score_categories_placement_cell_is_not_placement_context():
    # "Training and Placement Cell" is an organiser, not a recruitment signal, so it must not
    # license a brand keyword. This is the precise mechanism behind the yoga misfiling.
    cfg = {
        "category_keywords": {"P": ["google"]},
        "conditional_keywords": mail_ingest.DEFAULT_CONFIG["conditional_keywords"],
    }
    body = "The Training and Placement Cell is organising this. Register via the Google Form."
    assert dict(mail_ingest.score_categories("", body, "", cfg))["P"] == 0.0


def test_score_categories_subject_negative_keyword_vetoes_category():
    cfg = {
        "category_keywords": {"P": ["placement", "interview", "drive"]},
        "category_negative_keywords": {"P": ["yoga"]},
    }
    scored = mail_ingest.score_categories(
        "Yoga Competition", "Placement Cell interview drive", "", cfg
    )
    assert dict(scored)["P"] == 0.0


def test_score_categories_body_negative_keyword_only_penalizes():
    cfg = {
        "category_keywords": {"P": ["placement", "interview", "drive"]},
        "category_negative_keywords": {"P": ["nss"]},
    }
    scored = mail_ingest.score_categories(
        "Placement interview drive", "organised with nss", "", cfg
    )
    assert 0.0 < dict(scored)["P"] < 9.0  # penalised, not vetoed


def test_score_categories_ranks_the_yoga_email_as_general_college():
    ranked = mail_ingest.score_categories(
        _YOGA_EMAIL["subject"], _YOGA_EMAIL["body_text"], _YOGA_EMAIL["from"], _defaults()
    )
    assert ranked[0][0] == "General College"
    assert dict(ranked)["Placements"] == 0.0


def test_score_categories_truncates_the_body():
    cfg = {"category_keywords": {"P": ["internship"]}}
    body = ("x " * mail_ingest.BODY_CHAR_LIMIT) + "internship"
    assert dict(mail_ingest.score_categories("", body, "", cfg))["P"] == 0.0


# --- Arbitration ------------------------------------------------------------------------

_KNOWN = {"Placements", "General College", "Lectures & Profs"}


def test_arbitrate_confident_agreement_is_high():
    ranked = [("Placements", 9.0), ("General College", 0.0)]
    assert mail_ingest.arbitrate_category("Placements", ranked, _KNOWN) == ("Placements", "high")


def test_arbitrate_confident_disagreement_overrides_the_llm_at_medium():
    ranked = [("Placements", 9.0), ("General College", 0.0)]
    assert mail_ingest.arbitrate_category("Academics", ranked, _KNOWN) == ("Placements", "medium")


def test_arbitrate_ambiguous_margin_lets_the_llm_break_the_tie():
    ranked = [("Placements", 4.0), ("General College", 3.0)]
    verdict = mail_ingest.arbitrate_category("General College", ranked, _KNOWN)
    assert verdict == ("General College", "high")


def test_arbitrate_ambiguous_margin_with_an_outside_llm_answer_is_low():
    ranked = [("Placements", 4.0), ("General College", 3.0)]
    assert mail_ingest.arbitrate_category("Sports", ranked, _KNOWN) == ("Placements", "low")


def test_arbitrate_no_signal_with_a_known_llm_category_is_medium():
    ranked = [("Placements", 0.0), ("General College", 0.0)]
    assert mail_ingest.arbitrate_category("Placements", ranked, _KNOWN) == ("Placements", "medium")


def test_arbitrate_no_signal_with_an_invented_llm_category_is_low():
    ranked = [("Placements", 0.0), ("General College", 0.0)]
    assert mail_ingest.arbitrate_category("Yoga Stuff", ranked, _KNOWN) == ("Yoga Stuff", "low")


# --- End-to-end ingest ------------------------------------------------------------------


def test_ingest_yoga_competition_email_is_filed_under_general_college(tmp_path, monkeypatch):
    # The reported bug: a college yoga competition must not land in Placements.
    conn = _conn(tmp_path)
    _fake_llm(monkeypatch, "Placements", topic="Yoga Competition")
    result = mail_ingest.ingest_email(conn, dict(_YOGA_EMAIL), _defaults())

    assert result["category"] == "General College"
    assert store.get(conn, "mail:cat:general-college") is not None
    assert store.get(conn, "mail:cat:placements") is None
    parents = store.neighbors(conn, result["thread_id"], "contains", incoming=True)
    assert len(parents) == 1
    assert parents[0]["id"] == "mail:topic:general-college:yoga-competition"


def test_ingest_off_campus_drive_email_is_still_placements(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    email = {
        "uid": "5", "from": "tpcell@college.edu", "to": "me@x.com",
        "subject": "Accenture Off-Campus Drive 2026",
        "body_text": (
            "Eligibility criteria: 7 CGPA. Stipend 25k, CTC 6 LPA. Shortlisted students will "
            "get an interview. Register via the Google Form."
        ),
        "attachments": [],
    }
    _fake_llm(monkeypatch, "General College", topic="Accenture")
    result = mail_ingest.ingest_email(conn, email, _defaults())
    assert result["category"] == "Placements"
    assert result["confidence"] == "medium"


def test_ingest_guest_lecture_email_is_lectures_and_profs(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    email = {
        "uid": "6", "from": "hod@college.edu", "to": "me@x.com",
        "subject": "Guest Lecture on Compilers",
        "body_text": "A guest lecture by a visiting professor. Register via the Google Form.",
        "attachments": [],
    }
    _fake_llm(monkeypatch, "Placements", topic="Compilers")
    result = mail_ingest.ingest_email(conn, email, _defaults())
    assert result["category"] == "Lectures & Profs"


def test_ingest_sports_day_organised_by_placement_cell_is_general_college(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    email = {
        "uid": "7", "from": "tpcell@college.edu", "to": "me@x.com",
        "subject": "Annual Sports Day 2026",
        "body_text": "Organised by the Training and Placement Cell. Register via Google Form.",
        "attachments": [],
    }
    _fake_llm(monkeypatch, "Placements", topic="Sports Day")
    result = mail_ingest.ingest_email(conn, email, _defaults())
    assert result["category"] == "General College"


def test_ingest_low_confidence_thread_is_flagged_for_review(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    # Deliberately hits no keyword in any category, so the vocabulary has nothing to say and
    # the LLM invents a category — row 6 of the arbitration table.
    email = {
        "uid": "8", "from": "office@college.edu", "to": "me@x.com",
        "subject": "Regarding your query", "body_text": "Please see the attached document.",
        "attachments": [],
    }
    _fake_llm(monkeypatch, "Totally Invented Category", topic="Query")
    result = mail_ingest.ingest_email(conn, email, _defaults())
    assert result["confidence"] == "low"
    assert store.get(conn, result["thread_id"])["needs_review"] == 1


def test_ingest_records_classification_provenance(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    _fake_llm(monkeypatch, "Placements", topic="Yoga Competition")
    result = mail_ingest.ingest_email(conn, dict(_YOGA_EMAIL), _defaults())
    recorded = store.get(conn, result["thread_id"])["data"]["classification"]
    assert recorded["category"] == "General College"
    assert recorded["llm_category"] == "Placements"
    assert recorded["keyword_category"] == "General College"
    assert "General College" in recorded["scores"]


def test_ingest_overridden_category_replaces_a_topic_echoing_the_llm_category(
    tmp_path, monkeypatch
):
    conn = _conn(tmp_path)
    email = _email(uid="11", subject="Accenture Off-Campus Drive - interview shortlisted")
    # LLM says Academics AND names the topic "Academics" — meaningless once we override.
    _fake_llm(monkeypatch, "Academics", topic="Academics")
    result = mail_ingest.ingest_email(conn, email, _defaults())
    assert result["category"] == "Placements"
    assert result["topic"] == "Accenture Off-Campus Drive - interview shortlisted"


# --- Config -----------------------------------------------------------------------------


def test_load_config_deep_merges_category_keywords_per_category(tmp_path):
    path = tmp_path / "mail_config.json"
    path.write_text(json.dumps({"category_keywords": {"Placements": ["x"]}}), encoding="utf-8")
    cfg = mail_ingest.load_config(path)
    assert cfg["category_keywords"]["Placements"] == ["x"]
    # ...and the other categories keep their defaults instead of being wiped.
    assert "yoga" in cfg["category_keywords"]["General College"]


def test_load_config_does_not_mutate_the_module_defaults(tmp_path):
    cfg = mail_ingest.load_config(tmp_path / "nope.json")
    cfg["category_keywords"]["Placements"].append("polluted")
    assert "polluted" not in mail_ingest.DEFAULT_CONFIG["category_keywords"]["Placements"]


def test_load_config_defaults_include_negative_and_conditional_keywords(tmp_path):
    cfg = mail_ingest.load_config(tmp_path / "nope.json")
    assert "yoga" in cfg["category_negative_keywords"]["Placements"]
    assert "google" in cfg["conditional_keywords"]


# --- Reclassification helpers -----------------------------------------------------------


def test_prune_empty_mail_nodes_removes_childless_topics_and_categories(tmp_path):
    conn = _conn(tmp_path)
    mail_ingest.ensure_topic(conn, "Placements", "Ghost Topic")
    assert store.get(conn, "mail:topic:placements:ghost-topic") is not None
    removed = mail_ingest.prune_empty_mail_nodes(conn)
    assert "mail:topic:placements:ghost-topic" in removed
    assert "mail:cat:placements" in removed
    assert store.get(conn, "mail:cat:placements") is None


def test_prune_empty_mail_nodes_keeps_populated_branches(tmp_path):
    conn = _conn(tmp_path)
    topic_id = mail_ingest.ensure_topic(conn, "Placements", "Acme")
    store.upsert(
        conn, "mail_thread", {"source_id": "mail:thread:1", "title": "t"},
        title="t", summary="s", source="mail:1",
    )
    store.add_edge(conn, topic_id, "mail:thread:1", "contains")
    assert mail_ingest.prune_empty_mail_nodes(conn) == []
    assert store.get(conn, "mail:cat:placements") is not None


# --- Learning from manual corrections ---------------------------------------------------


def test_learnable_tokens_drops_noise():
    tokens = mail_ingest._learnable_tokens("Yoga Competition 2026 on the 12th")
    assert "yoga" in tokens
    assert "competition" in tokens
    assert "2026" not in tokens  # bare years carry no category signal
    assert "on" not in tokens  # stopword
    assert "the" not in tokens


def test_learn_category_keywords_stores_and_merges(tmp_path):
    conn = _conn(tmp_path)
    first = mail_ingest.learn_category_keywords(conn, "General College", "Yoga Competition 2026")
    assert "yoga" in first

    second = mail_ingest.learn_category_keywords(conn, "General College", "Zumba Session")
    # Merges with what was already learned rather than replacing it.
    assert "yoga" in second
    assert "zumba" in second


def test_learned_keywords_are_scoped_per_category(tmp_path):
    conn = _conn(tmp_path)
    mail_ingest.learn_category_keywords(conn, "General College", "Yoga Competition")
    mail_ingest.learn_category_keywords(conn, "Placements", "Cognizant Recruitment")
    learned = mail_ingest.learned_keywords(conn)
    assert "yoga" in learned["General College"]
    assert "cognizant" in learned["Placements"]
    assert "yoga" not in learned["Placements"]


def test_config_with_learned_extends_without_losing_defaults(tmp_path):
    conn = _conn(tmp_path)
    mail_ingest.learn_category_keywords(conn, "General College", "Sangeet Night")
    merged = mail_ingest.config_with_learned(conn, _defaults())
    general = merged["category_keywords"]["General College"]
    assert "sangeet" in general  # learned
    assert "yoga" in general  # still has the built-in defaults
    assert "placement" in merged["category_keywords"]["Placements"]


def test_config_with_learned_is_a_noop_without_corrections(tmp_path):
    conn = _conn(tmp_path)
    config = _defaults()
    assert mail_ingest.config_with_learned(conn, config) is config


def test_learned_keywords_steer_a_later_email(tmp_path, monkeypatch):
    """A word the user taught us should carry a later, otherwise-unknown email."""
    conn = _conn(tmp_path)
    # "sangeet" is in no default vocabulary, so this email has no signal at all...
    email = {
        "uid": "301", "from": "office@college.edu", "to": "me@x.com",
        "subject": "Sangeet auditions", "body_text": "Auditions will be held shortly.",
        "attachments": [],
    }
    _fake_llm(monkeypatch, "Placements", topic="Sangeet")
    before = mail_ingest.score_categories(
        email["subject"], email["body_text"], email["from"], _defaults()
    )
    assert dict(before)["General College"] == 0.0

    # ...until the user corrects a similar mail into General College.
    mail_ingest.learn_category_keywords(conn, "General College", "Sangeet Night")
    after = mail_ingest.score_categories(
        email["subject"],
        email["body_text"],
        email["from"],
        mail_ingest.config_with_learned(conn, _defaults()),
    )
    assert dict(after)["General College"] > 0.0

    result = mail_ingest.ingest_email(conn, email, _defaults())
    assert result["category"] == "General College"


def test_a_corrected_thread_is_not_dragged_back_by_a_later_email(tmp_path, monkeypatch):
    """The regression that would quietly undo every manual fix.

    The category is computed before the merge decision and reparent_thread re-files the whole
    thread, so without a pin a follow-up email scored as Placements would drag a thread the
    user had moved to General College straight back.
    """
    conn = _conn(tmp_path)
    thread_id = "mail:thread:401"

    # The user has already moved this thread to General College by hand.
    topic_id = mail_ingest.ensure_topic(conn, "General College", "Yoga Competition")
    store.upsert(
        conn,
        "mail_thread",
        {
            "source_id": thread_id,
            "title": "Yoga Competition 2026",
            "body": "b",
            "source_uids": ["401"],
            "classification": {
                "category": "General College",
                "confidence": "high",
                "corrected_by_user": True,
                "auto_category": "Placements",
            },
        },
        title="Yoga Competition 2026",
        summary="s",
        source="mail:401",
        needs_review=False,
    )
    store.add_edge(conn, topic_id, thread_id, "contains")

    # A follow-up arrives that scores overwhelmingly as Placements and merges into that thread.
    follow_up = {
        "uid": "402", "from": "tpcell@college.edu", "to": "me@x.com",
        "subject": "Accenture Off-Campus Drive - interview shortlisted",
        "body_text": "Eligibility criteria and stipend details.",
        "attachments": [],
    }
    _fake_llm(monkeypatch, "Placements", topic="Accenture")
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "merge", "merge_into_id": thread_id, "summary": "s", "body": "b",
        },
    )
    result = mail_ingest.ingest_email(conn, follow_up, _defaults())

    assert result["category"] == "General College"
    parents = store.neighbors(conn, thread_id, "contains", incoming=True)
    assert len(parents) == 1
    assert parents[0]["id"] == "mail:topic:general-college:yoga-competition"
    # ...and the pin survives for the next email too.
    assert store.get(conn, thread_id)["data"]["classification"]["corrected_by_user"] is True


def test_an_uncorrected_thread_still_gets_reclassified_on_merge(tmp_path, monkeypatch):
    """The pin must not freeze threads the user never touched."""
    conn = _conn(tmp_path)
    thread_id = "mail:thread:501"
    topic_id = mail_ingest.ensure_topic(conn, "General College", "Something")
    store.upsert(
        conn, "mail_thread",
        {"source_id": thread_id, "title": "Something", "body": "b", "source_uids": ["501"]},
        title="Something", summary="s", source="mail:501",
    )
    store.add_edge(conn, topic_id, thread_id, "contains")

    follow_up = {
        "uid": "502", "from": "tpcell@college.edu", "to": "me@x.com",
        "subject": "Accenture Off-Campus Drive - interview shortlisted",
        "body_text": "Eligibility criteria and stipend details.",
        "attachments": [],
    }
    _fake_llm(monkeypatch, "Placements", topic="Accenture")
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "merge", "merge_into_id": thread_id, "summary": "s", "body": "b",
        },
    )
    result = mail_ingest.ingest_email(conn, follow_up, _defaults())
    assert result["category"] == "Placements"


# --- Attachments are persisted on the thread ---------------------------------------------


def _xlsx(tmp_path, rows, name="shortlist.xlsx"):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    path = tmp_path / name
    wb.save(str(path))
    return path


def test_ingest_persists_attachment_findings(tmp_path, monkeypatch):
    """Findings used to be fed to the ingest prompts and discarded, so Q&A could never see
    them. They must survive on the thread."""
    conn = _conn(tmp_path)
    sheet = _xlsx(tmp_path, [["Reg No", "Name"], ["23BCE1234", "Adidev Anand"]])
    email = {
        "uid": "601", "from": "tpcell@college.edu", "to": "me@x.com",
        "subject": "Hevo Data shortlist",
        "body_text": "The shortlist is attached.",
        "attachments": [{"saved_to": str(sheet)}],
    }
    _fake_llm(monkeypatch, "Placements", topic="Hevo Data")
    config = {**_defaults(), "identifiers": ["23BCE1234"]}

    result = mail_ingest.ingest_email(conn, email, config)

    stored = store.get(conn, result["thread_id"])["data"]["attachments"]
    assert len(stored) == 1
    assert stored[0]["file"] == "shortlist.xlsx"
    assert stored[0]["mentions_you"] == ["23BCE1234"]


def test_ingest_reports_when_a_shortlist_omits_you(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    sheet = _xlsx(tmp_path, [["Reg No", "Name"], ["23BCE0001", "Someone Else"]])
    email = {
        "uid": "602", "from": "tpcell@college.edu", "to": "me@x.com",
        "subject": "Shortlist", "body_text": "Attached.",
        "attachments": [{"saved_to": str(sheet)}],
    }
    _fake_llm(monkeypatch, "Placements", topic="Shortlist")
    config = {**_defaults(), "identifiers": ["23BCE1234"]}

    result = mail_ingest.ingest_email(conn, email, config)
    stored = store.get(conn, result["thread_id"])["data"]["attachments"]
    assert stored[0]["mentions_you"] == []
    assert "not listed" in stored[0]["finding"]


def test_merged_thread_keeps_attachments_from_earlier_emails(tmp_path, monkeypatch):
    """The shortlist naming you may have arrived in the first email of a thread."""
    conn = _conn(tmp_path)
    sheet = _xlsx(tmp_path, [["Reg No"], ["23BCE1234"]])
    config = {**_defaults(), "identifiers": ["23BCE1234"]}
    _fake_llm(monkeypatch, "Placements", topic="Hevo Data")

    first = {
        "uid": "603", "from": "tpcell@college.edu", "to": "me@x.com",
        "subject": "Hevo shortlist", "body_text": "Attached.",
        "attachments": [{"saved_to": str(sheet)}],
    }
    thread_id = mail_ingest.ingest_email(conn, first, config)["thread_id"]

    # A follow-up with no attachment merges into the same thread.
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "merge", "merge_into_id": thread_id, "summary": "s", "body": "b",
        },
    )
    second = {
        "uid": "604", "from": "tpcell@college.edu", "to": "me@x.com",
        "subject": "Hevo shortlist — interview slots", "body_text": "Slots below.",
        "attachments": [],
    }
    mail_ingest.ingest_email(conn, second, config)

    stored = store.get(conn, thread_id)["data"]["attachments"]
    assert [a["file"] for a in stored] == ["shortlist.xlsx"]
    assert stored[0]["mentions_you"] == ["23BCE1234"]


def test_attachment_identifiers_come_from_the_stored_profile(tmp_path, monkeypatch):
    """The whole point of moving the profile server-side: adding your name in the UI is enough
    to make attachment matching work, with no config file to edit."""
    conn = _conn(tmp_path)
    brain_profile.save_profile(conn, [{"key": "Roll no", "value": "23BCE1234"}])

    sheet = _xlsx(tmp_path, [["Reg No", "Name"], ["23BCE1234", "Adidev Anand"]])
    email = {
        "uid": "701", "from": "tpcell@college.edu", "to": "me@x.com",
        "subject": "Hevo Data shortlist", "body_text": "Attached.",
        "attachments": [{"saved_to": str(sheet)}],
    }
    _fake_llm(monkeypatch, "Placements", topic="Hevo Data")

    # Note the config carries NO identifiers — the profile is the only source.
    result = mail_ingest.ingest_email(conn, email, _defaults())

    stored = store.get(conn, result["thread_id"])["data"]["attachments"]
    assert stored[0]["mentions_you"] == ["23BCE1234"]


def test_a_non_identity_profile_row_is_not_used_for_matching(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    # "Placements" as a team name must not make every shortlist look like it names you.
    brain_profile.save_profile(conn, [{"key": "Team", "value": "Placements"}])

    sheet = _xlsx(tmp_path, [["Dept"], ["Placements"]])
    email = {
        "uid": "702", "from": "tpcell@college.edu", "to": "me@x.com",
        "subject": "Dept list", "body_text": "Attached.",
        "attachments": [{"saved_to": str(sheet)}],
    }
    _fake_llm(monkeypatch, "Placements", topic="Dept list")

    result = mail_ingest.ingest_email(conn, email, _defaults())
    stored = store.get(conn, result["thread_id"])["data"]["attachments"]
    assert stored[0]["mentions_you"] == []


# --- Ingest progress events --------------------------------------------------------------


def _two_emails(monkeypatch, subjects=("First mail", "Second mail")):
    emails = [
        {"uid": str(i), "from": "a@b.com", "to": "me@x.com", "subject": s,
         "body_text": "...", "attachments": []}
        for i, s in enumerate(subjects, start=1)
    ]
    monkeypatch.setattr(
        mail_ingest, "fetch_unread_emails", lambda since_minutes=None, user_id=None: emails
    )
    monkeypatch.setattr(mail_ingest, "mark_email_read", lambda uid, user_id=None: None)
    monkeypatch.setattr(mail_ingest, "load_config", lambda: _defaults())
    return emails


def test_run_iter_reports_a_total_before_any_work(tmp_path, monkeypatch):
    """The bar needs an honest denominator before the slow part starts."""
    conn = _conn(tmp_path)
    _two_emails(monkeypatch)
    _fake_llm(monkeypatch, "Placements", topic="T")

    events = list(mail_ingest.run_iter(conn))
    assert events[0]["stage"] == "connecting"
    assert events[1] == {"stage": "fetched", "total": 2}


def test_run_iter_counts_each_email_exactly_once(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    _two_emails(monkeypatch)
    _fake_llm(monkeypatch, "Placements", topic="T")

    events = list(mail_ingest.run_iter(conn))
    completed = [e for e in events if e["stage"] == "ingested"]
    assert [e["done"] for e in completed] == [1, 2]
    assert all(e["total"] == 2 for e in completed)
    # Progress never claims completion before the work is done.
    assert all(e["done"] <= e["total"] for e in completed)


def test_run_iter_names_the_email_being_worked_on(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    _two_emails(monkeypatch, subjects=("Accenture drive", "Yoga day"))
    _fake_llm(monkeypatch, "Placements", topic="T")

    events = list(mail_ingest.run_iter(conn))
    starting = [e for e in events if e["stage"] == "ingesting"]
    assert [e["subject"] for e in starting] == ["Accenture drive", "Yoga day"]
    # "ingesting" is emitted before the work, so its count is the *previous* completion.
    assert [e["done"] for e in starting] == [0, 1]


def test_run_iter_ends_with_the_full_result_set(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    _two_emails(monkeypatch)
    _fake_llm(monkeypatch, "Placements", topic="T")

    final = list(mail_ingest.run_iter(conn))[-1]
    assert final["stage"] == "done"
    assert final["processed"] == 2
    assert len(final["results"]) == 2


def test_run_iter_keeps_going_after_one_bad_email(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    _two_emails(monkeypatch)
    _fake_llm(monkeypatch, "Placements", topic="T")

    calls = {"n": 0}

    def flaky(conn_, email, config):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return {"uid": email["uid"], "category": "C", "topic": "T",
                "thread_id": "mail:thread:2", "action": "new", "confidence": "high"}

    monkeypatch.setattr(mail_ingest, "ingest_email", flaky)
    events = list(mail_ingest.run_iter(conn))

    failed = [e for e in events if e["stage"] == "ingested" and e.get("error")]
    assert len(failed) == 1
    # The failure still advances the bar — otherwise it would stall at 50% forever.
    assert failed[0]["done"] == 1
    assert events[-1]["stage"] == "done"
    assert events[-1]["processed"] == 2


def test_run_still_returns_just_the_results(tmp_path, monkeypatch):
    """The CLI and existing callers must not notice the refactor."""
    conn = _conn(tmp_path)
    _two_emails(monkeypatch)
    _fake_llm(monkeypatch, "Placements", topic="T")

    results = mail_ingest.run(conn)
    assert len(results) == 2
    assert all("uid" in r for r in results)


# --- Sender precedent: identical mail must not scatter ------------------------------------


def _filed(conn, thread_id, sender, category, *, corrected=False):
    store.upsert(
        conn, "mail_thread",
        {"source_id": thread_id, "title": "t", "sender": sender,
         "classification": {"category": category, "corrected_by_user": corrected}},
        title="t", summary="s", source="mail",
    )


def test_sender_precedent_is_none_without_history(tmp_path):
    assert mail_ingest.sender_precedent(_conn(tmp_path), "a@b.com") is None


def test_sender_precedent_finds_where_that_sender_was_filed(tmp_path):
    conn = _conn(tmp_path)
    _filed(conn, "mail:thread:1", "Google <no-reply@accounts.google.com>", "Security Alerts")
    assert (
        mail_ingest.sender_precedent(conn, "no-reply@accounts.google.com") == "Security Alerts"
    )


def test_sender_precedent_ignores_the_display_name(tmp_path):
    """"Google <x@y>" and "Google Accounts <x@y>" are the same sender."""
    conn = _conn(tmp_path)
    _filed(conn, "mail:thread:1", "Google <no-reply@accounts.google.com>", "Security Alerts")
    assert (
        mail_ingest.sender_precedent(conn, "Google Accounts <NO-REPLY@Accounts.Google.com>")
        == "Security Alerts"
    )


def test_sender_precedent_does_not_bleed_across_senders(tmp_path):
    conn = _conn(tmp_path)
    _filed(conn, "mail:thread:1", "no-reply@accounts.google.com", "Security Alerts")
    assert mail_ingest.sender_precedent(conn, "tpcell@college.edu") is None


def test_a_human_correction_outweighs_repeated_auto_filings(tmp_path):
    conn = _conn(tmp_path)
    for i in range(3):
        _filed(conn, f"mail:thread:{i}", "no-reply@accounts.google.com", "Placements")
    _filed(conn, "mail:thread:9", "no-reply@accounts.google.com", "Security Alerts",
           corrected=True)
    assert (
        mail_ingest.sender_precedent(conn, "no-reply@accounts.google.com") == "Security Alerts"
    )


def test_precedent_decides_when_keywords_have_nothing_to_say():
    """The exact hole: zero keyword signal used to hand the choice to a weak model."""
    ranked = [("General College", 0.0), ("Placements", 0.0)]
    # Without precedent the LLM's invented category wins, and is flagged for review.
    assert mail_ingest.arbitrate_category("Whatever", ranked, {"Placements"}) == (
        "Whatever", "low",
    )
    # With precedent the answer is deterministic and the LLM is ignored.
    assert mail_ingest.arbitrate_category(
        "Whatever", ranked, {"Placements"}, sender_category="Security Alerts"
    ) == ("Security Alerts", "medium")


def test_precedent_does_not_override_a_confident_keyword_verdict():
    """A drive email from a sender you usually get notifications from is still a drive."""
    ranked = [("Placements", 12.0), ("General College", 0.0)]
    assert mail_ingest.arbitrate_category(
        "Placements", ranked, {"Placements"}, sender_category="Security Alerts"
    ) == ("Placements", "high")


def test_precedent_breaks_an_ambiguous_tie_the_llm_cannot():
    ranked = [("Placements", 4.0), ("General College", 3.0)]
    # LLM answered outside the shortlist, so precedent is the better anchor.
    assert mail_ingest.arbitrate_category(
        "Nonsense", ranked, {"Placements"}, sender_category="General College"
    ) == ("General College", "medium")


def test_two_identical_emails_from_one_sender_land_together(tmp_path, monkeypatch):
    """The reported symptom, end to end: same sender, same mail, one destination."""
    conn = _conn(tmp_path)
    alert = {
        "uid": "1", "from": "Google <no-reply@accounts.google.com>", "to": "me@x.com",
        "subject": "Security alert",
        "body_text": "A new sign-in to your Google Account.", "attachments": [],
    }
    # The model is unstable on this mail — a different answer each time.
    answers = iter(["Security Alerts", "Placements"])
    monkeypatch.setattr(
        mail_ingest, "classify_email",
        lambda e, f, c: {"category": next(answers), "new_category": True,
                         "topic": "Google Account", "new_topic": True},
    )
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda e, f, x: {"action": "new", "merge_into_id": None, "summary": "s", "body": "b"},
    )

    first = mail_ingest.ingest_email(conn, dict(alert), _defaults())
    second = mail_ingest.ingest_email(conn, {**alert, "uid": "2"}, _defaults())

    # The model said "Placements" the second time; precedent overruled it.
    assert first["category"] == "Security Alerts"
    assert second["category"] == "Security Alerts"


# --- Re-scanning attachments after identifiers change ------------------------------------


def test_rescan_finds_you_after_an_identifier_is_added(tmp_path, monkeypatch):
    """The real failure: a shortlist ingested before you entered your roll number kept
    reporting "not listed" forever."""
    conn = _conn(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(mail_ingest, "ATTACHMENT_CACHE", cache)

    sheet = _xlsx(cache, [["NEOID"], ["A1B2C3D4"], ["T7M8V0L5"]], name="601__shortlist.xlsx")
    assert sheet.exists()

    # Ingested while the profile knew only a name that does not appear in the sheet.
    brain_profile.save_profile(conn, [{"key": "Name", "value": "Adidev Anand"}])
    email = {
        "uid": "601", "from": "tpcell@college.edu", "to": "me@x.com",
        "subject": "Shortlist", "body_text": "Attached.",
        "attachments": [{"saved_to": str(sheet)}],
    }
    _fake_llm(monkeypatch, "Placements", topic="Shortlist")
    result = mail_ingest.ingest_email(conn, email, _defaults())
    assert store.get(conn, result["thread_id"])["data"]["attachments"][0]["mentions_you"] == []

    # Now the Neo ID is added — past mail must be re-evaluated, not left stale.
    brain_profile.save_profile(
        conn,
        [{"key": "Name", "value": "Adidev Anand"}, {"key": "Neo ID", "value": "T7M8V0L5"}],
    )
    changed = mail_ingest.rescan_attachments(conn, _defaults())

    assert [c["now_mentions"] for c in changed] == [["T7M8V0L5"]]
    stored = store.get(conn, result["thread_id"])["data"]["attachments"][0]
    assert stored["mentions_you"] == ["T7M8V0L5"]
    assert stored["finding"][0]["values"]["NEOID"] == "T7M8V0L5"


def test_rescan_reports_nothing_when_the_answer_is_unchanged(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(mail_ingest, "ATTACHMENT_CACHE", cache)
    _xlsx(cache, [["NEOID"], ["T7M8V0L5"]], name="602__shortlist.xlsx")

    brain_profile.save_profile(conn, [{"key": "Neo ID", "value": "T7M8V0L5"}])
    email = {
        "uid": "602", "from": "x@y.com", "to": "me@x.com", "subject": "S",
        "body_text": "Attached.",
        "attachments": [{"saved_to": str(cache / "602__shortlist.xlsx")}],
    }
    _fake_llm(monkeypatch, "Placements", topic="S")
    mail_ingest.ingest_email(conn, email, _defaults())

    # Same identifiers, so nothing to report — a rescan must be quiet, not noisy.
    assert mail_ingest.rescan_attachments(conn, _defaults()) == []


def test_rescan_preserves_the_rest_of_the_thread(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(mail_ingest, "ATTACHMENT_CACHE", cache)
    _xlsx(cache, [["NEOID"], ["T7M8V0L5"]], name="603__shortlist.xlsx")

    email = {
        "uid": "603", "from": "x@y.com", "to": "me@x.com", "subject": "Keep my body",
        "body_text": "Attached.",
        "attachments": [{"saved_to": str(cache / "603__shortlist.xlsx")}],
    }
    _fake_llm(monkeypatch, "Placements", topic="S")
    tid = mail_ingest.ingest_email(conn, email, _defaults())["thread_id"]
    before = store.get(conn, tid)["data"]

    brain_profile.save_profile(conn, [{"key": "Neo ID", "value": "T7M8V0L5"}])
    mail_ingest.rescan_attachments(conn, _defaults())

    after = store.get(conn, tid)["data"]
    assert after["body"] == before["body"]
    assert after["source_uids"] == before["source_uids"]
    assert after["classification"] == before["classification"]


def test_cached_attachments_are_matched_by_uid(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(mail_ingest, "ATTACHMENT_CACHE", cache)
    (cache / "700__a.xlsx").write_text("x")
    (cache / "700__b.pdf").write_text("x")
    (cache / "701__other.xlsx").write_text("x")

    names = [p.name for p in mail_ingest.cached_attachments_for(["700"])]
    assert names == ["700__a.xlsx", "700__b.pdf"]
