"""Interactive Slack bot — ask the brain from Slack, get the answer + its sources.

Uses **Socket Mode** (a WebSocket the bot opens to Slack) so it needs no public URL / tunnel — just two
tokens. Two ways to ask:
    /brain who is the best fit for backend?      (slash command)
    @brain what's overdue?                        (mention the bot)

Run it (after filling `.env` — see INTEGRATIONS.md):
    uv run python -m slack.bot

`format_answer` is pure (answer dict -> Slack text) so it's unit-testable without a live connection.
"""

from __future__ import annotations

import os
from typing import Any

from brain import ask as brain_ask
from brain import store


def format_answer(res: dict[str, Any]) -> str:
    """Turn an ask() result into a Slack message: the answer, then the node path it walked."""
    lines = [res.get("answer") or "(no answer)"]
    path = res.get("path") or []
    if path:
        lines.append("")
        lines.append("*Sources — the path I walked:* " + ", ".join(f"{n['type']}: {n['title']}" for n in path))
    return "\n".join(lines)


def _answer(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "Ask me something, e.g. `/brain who's the best fit for backend?`"
    return format_answer(brain_ask.ask(store.connect(), question))


def main() -> None:
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not bot_token or not app_token:
        raise SystemExit("Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in .env (see INTEGRATIONS.md).")

    from slack_bolt import App  # lazy: only needed to actually run the bot
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app = App(token=bot_token)

    @app.command("/brain")
    def handle_command(ack: Any, command: dict[str, Any], respond: Any) -> None:
        ack()
        respond(_answer(command.get("text", "")))

    @app.event("app_mention")
    def handle_mention(event: dict[str, Any], say: Any) -> None:
        text = event.get("text", "")
        question = text.split(">", 1)[-1] if ">" in text else text  # drop the leading @mention
        say(_answer(question))

    print("Brain bot online (Socket Mode). Try /brain or @-mention it.")
    SocketModeHandler(app, app_token).start()


if __name__ == "__main__":
    main()
