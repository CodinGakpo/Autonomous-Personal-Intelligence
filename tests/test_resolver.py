"""Tests for the deterministic write-path resolver."""

from brain.resolver import natural_key, normalize, resolve


def _existing():
    return [
        {"id": "T1", "name": "Fix the login bug", "assignee": "Sai"},
        {"id": "T2", "clickup_id": "CU-101", "name": "Secure API routes", "assignee": "Pruthvik"},
    ]


def test_new_task_creates():
    r = resolve({"name": "Write onboarding docs", "assignee": "Priya"}, _existing())
    assert r.action == "create"
    assert r.matched_id is None


def test_same_task_updates():
    r = resolve({"name": "Fix the login bug", "assignee": "Sai"}, _existing())
    assert r.action == "update"
    assert r.matched_id == "T1"


def test_normalization_matches_despite_case_and_punctuation():
    r = resolve({"name": "  fix the LOGIN bug!! ", "assignee": "Sai "}, _existing())
    assert r.action == "update"
    assert r.matched_id == "T1"


def test_source_id_match_updates_regardless_of_text():
    r = resolve({"clickup_id": "CU-101", "name": "totally different wording", "assignee": "x"}, _existing())
    assert r.action == "update"
    assert r.matched_id == "T2"
    assert r.key == "CU-101"


def test_source_id_new_creates():
    r = resolve({"clickup_id": "CU-999", "name": "New thing", "assignee": "x"}, _existing())
    assert r.action == "create"
    assert r.key == "CU-999"


def test_near_duplicate_same_assignee_flags_review():
    # "Fix login bug" vs existing "Fix the login bug", same assignee -> review, not silent merge.
    r = resolve({"name": "Fix login bug", "assignee": "Sai"}, _existing())
    assert r.action == "review"
    assert r.matched_id == "T1"


def test_same_name_different_assignee_not_merged():
    r = resolve({"name": "Fix the login bug", "assignee": "Priya"}, _existing())
    assert r.action == "create"


def test_natural_key_is_stable_and_order_independent():
    assert natural_key("Fix the login bug", "Sai") == natural_key("fix the  login bug", " sai ")
    assert normalize("Hello, World!") == "hello world"
