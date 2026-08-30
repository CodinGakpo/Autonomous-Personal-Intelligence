"""Slack outbound client — post a message to a channel.

Safe by default: with no `SLACK_BOT_TOKEN` (or no channel) it runs **dry-run** — it prints what it would
send and touches no network. Drop a bot token + channel into `.env` and it goes live. Mirrors the
`clickup/` client shape: one typed class, credentials from the environment, nothing else.

    from slack.client import SlackClient
    SlackClient().post("hello")            # dry-run unless SLACK_BOT_TOKEN + SLACK_CHANNEL are set
"""

from __future__ import annotations

import os
from typing import Any


class SlackClient:
    def __init__(self, token: str | None = None, *, default_channel: str | None = None) -> None:
        self._token = token if token is not None else os.environ.get("SLACK_BOT_TOKEN", "")
        self.default_channel = default_channel or os.environ.get("SLACK_CHANNEL", "")
        # dry-run whenever we lack the means to actually post
        self.dry_run = not self._token

    def post(self, text: str, channel: str | None = None) -> dict[str, Any]:
        """Post `text` to `channel` (or the default). Returns a small result dict; never raises on dry-run."""
        ch = channel or self.default_channel
        if self.dry_run or not ch:
            print(f"[slack dry-run] #{ch or '?'}: {text}")
            return {"dry_run": True, "channel": ch, "text": text}

        from slack_sdk import WebClient  # lazy: only needed to actually post

        resp = WebClient(token=self._token).chat_postMessage(channel=ch, text=text)
        return {"ok": bool(resp.get("ok")), "channel": ch, "ts": resp.get("ts")}
