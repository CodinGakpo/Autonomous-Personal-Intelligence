"""Announce brain events to Slack — the glue between what the brain does and the channel.

`notify(event, **data)` formats a short line and posts it via `slack.client.SlackClient` (dry-run until a
token + channel exist). It **never breaks the caller**: any Slack failure is swallowed and logged, because
posting a notification must not fail a résumé ingest or a ClickUp push.
"""

from __future__ import annotations

from typing import Any, Callable

from slack.client import SlackClient


def _candidate_added(d: dict[str, Any]) -> str:
    role = d.get("role") or "no target role"
    return f":busts_in_silhouette: Candidate *{d.get('name')}* added to the brain ({d.get('action')}) - {role}."


def _tasks_pushed(d: dict[str, Any]) -> str:
    return f":white_check_mark: Pushed *{d.get('count')}* task(s) to ClickUp list `{d.get('list_id')}`."


_FORMATTERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "candidate_added": _candidate_added,
    "tasks_pushed": _tasks_pushed,
}


def notify(event: str, **data: Any) -> dict[str, Any] | None:
    """Format `event` and post it to Slack. Returns the post result (or None if it was skipped)."""
    try:
        fmt = _FORMATTERS.get(event)
        text = fmt(data) if fmt else f"{event}: {data}"
        return SlackClient().post(text)
    except Exception as exc:  # a broken notifier must never break the write path
        print(f"[notify] skipped '{event}': {exc}")
        return None
