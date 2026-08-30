# Connecting ClickUp & Slack

Everything runs **dry-run (no network) until you add tokens**. Copy `.env.example` → `.env`
(git-ignored) and fill in what you have. The code reads those values automatically.

> ⚠️ Never commit `.env` or paste tokens into chat. `.env` is git-ignored on purpose.

---

## 1. ClickUp  (push + pull)

### Get the credentials
- **API token** — ClickUp → avatar (bottom-left) → *Settings* → *Apps* → *API Token* → **Generate** → copy `pk_...`.
- **List ID** — open the List you want → *right-click its name → Copy link* (or read it from the URL `.../v/li/<LIST_ID>`).

### `.env`
```
CLICKUP_TOKEN=pk_xxxxxxxx
CLICKUP_LIST_ID=901234567
```

### Use it
- **Push** (brain action-items → ClickUp tasks):
  - dry-run (safe default): `uv run python -m brain.act`
  - live: `uv run python -m brain.act --push`
- **Pull** (ClickUp tasks → brain nodes): `uv run python -m brain.ingest clickup`
  - Idempotent: a task is keyed on its ClickUp id, so re-pulling **updates**, never duplicates. Push-then-pull reconciles the same task.

---

## 2. Slack

Two capabilities — set up whichever you want (or both).

### A. Notifications (outbound) — the brain posts to a channel
1. Create an app: https://api.slack.com/apps → *Create New App* → *From scratch* → name it, pick your workspace.
2. *OAuth & Permissions* → *Bot Token Scopes* → add **`chat:write`**.
3. *Install to Workspace* → copy the **Bot User OAuth Token** (`xoxb-...`).
4. In Slack, invite the bot to the channel: `/invite @YourApp`.
5. Channel id: click the channel name → the ID (`C0...`) is at the bottom of the popup.

```
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL=C0XXXXXXX
```

Smoke test: `uv run python -c "from slack.client import SlackClient; print(SlackClient().post('brain online'))"`
(no token → prints a dry-run line; with a token → actually posts).

Fires automatically on: **a candidate added** (GUI or CLI) and **tasks pushed to ClickUp**.

### B. Interactive `/brain` — ask the brain from Slack
Needs the bot token above **plus** an app-level token (Socket Mode — no public URL required).
1. Same app → *Socket Mode* → **Enable** → generate an **App-Level Token** with scope `connections:write` → copy `xapp-...`.
2. *Slash Commands* → *Create New Command* → command `/brain`, any description. (Socket Mode means no Request URL needed.)
3. *OAuth & Permissions* → add scopes `commands` (and `app_mentions:read` for @-mentions). Reinstall if prompted.
4. `.env`: `SLACK_APP_TOKEN=xapp-...`
5. Run the bot (keep it running): `uv run python -m slack.bot`
6. In Slack: `/brain who is the best fit for backend?` → it replies with the answer **and the sources it used**.

---

## What I need from you (summary)

| To turn on | You provide |
|---|---|
| ClickUp push + pull | `CLICKUP_TOKEN`, `CLICKUP_LIST_ID` |
| Slack notifications | `SLACK_BOT_TOKEN`, `SLACK_CHANNEL` (+ invite the bot to the channel) |
| Slack `/brain` bot | also `SLACK_APP_TOKEN` + create the `/brain` slash command |

Drop them into `.env` and tell me — I'll run the live smoke tests with you. Until then it's all built and dry-run-verified.
