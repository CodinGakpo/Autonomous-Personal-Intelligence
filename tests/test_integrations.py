"""Tests for the ClickUp/Slack integrations — the pure logic, no network, no tokens needed."""

from brain.ingest import _clickup_task_to_candidate
from brain import notify
from slack.bot import format_answer
from slack.client import SlackClient


def test_clickup_task_maps_to_candidate():
    task = {
        "id": "abc123",
        "name": "Fix the payments retry",
        "assignees": [{"username": "Sai", "email": "sai@x.com"}],
        "due_date": "1782000000000",           # ms epoch
        "priority": {"priority": "high"},
        "text_content": "retry logic + tests",
        "status": {"status": "open"},
        "url": "https://app.clickup.com/t/abc123",
    }
    c = _clickup_task_to_candidate(task)
    assert c["name"] == "Fix the payments retry"
    assert c["assignee"] == "Sai"
    assert c["clickup_id"] == "abc123"          # -> resolver keys on this, so re-pull updates not duplicates
    assert c["priority"] == "high"
    assert c["due_date"] and len(c["due_date"]) == 10   # ISO date YYYY-MM-DD


def test_clickup_task_tolerates_missing_fields():
    c = _clickup_task_to_candidate({"id": "x", "name": "bare"})
    assert c["assignee"] == "" and c["due_date"] is None and c["priority"] is None


def test_slack_client_is_dry_run_without_token():
    c = SlackClient(token="", default_channel="general")
    r = c.post("hello")
    assert r["dry_run"] is True
    assert r["text"] == "hello"


def test_notify_never_raises_and_returns_a_result():
    r = notify.notify("candidate_added", name="Sai", role="Backend", action="create")
    assert isinstance(r, dict)          # dry-run result dict, not an exception


def test_format_answer_includes_answer_and_sources():
    res = {"answer": "Sai is the best fit.", "path": [{"type": "person", "title": "Sai Prakash"}]}
    out = format_answer(res)
    assert "Sai is the best fit." in out
    assert "Sai Prakash" in out
