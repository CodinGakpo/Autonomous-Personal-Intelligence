# Setup — Mail Knowledge Tree

Get the mail knowledge-tree pipeline running on your own machine, against your own mailbox.

## 1. Prerequisites

- Python (version pinned in `.python-version`)
- [`uv`](https://docs.astral.sh/uv/) — dependency manager this project uses for everything
  (`uv sync`, `uv run ...`)

## 2. Clone & install

```bash
git clone <this-repo-url>
cd agent-os
uv sync
```

## 3. `.env` setup

```bash
cp .env.example .env
```

Open `.env` and fill in the mail-pipeline section (ClickUp/Slack vars are for other parts of
the project — leave them as placeholders if you're only using the mail pipeline).

## 4. Configuring your own mailbox

The pipeline reads mail over IMAP via `brain/emailtool.py` (vendored into this repo — no
external tools or accounts needed beyond your own mailbox).

**For Gmail** (most common case):

1. Turn on **2-Step Verification** on your Google Account, if it isn't already
   (Google Account → Security → 2-Step Verification).
2. Generate an **App Password**: Google Account → Security → App Passwords → create one
   (name it anything, e.g. "agent-os"). Copy the 16-character password it gives you — this is
   what goes in `EMAIL_APP_PASSWORD`, **not** your normal Gmail password (Gmail rejects IMAP
   logins with your normal password once 2FA is on).
3. Make sure IMAP is enabled: Gmail → Settings (gear icon) → **See all settings** →
   **Forwarding and POP/IMAP** tab → Enable IMAP → Save Changes.
4. In `.env`, set:
   ```
   EMAIL_EMAIL=you@gmail.com
   EMAIL_APP_PASSWORD=<the 16-character app password>
   EMAIL_IMAP_HOST=imap.gmail.com
   ```

**For other providers**: the same shape applies — an app-specific password (or your regular
password if the provider doesn't require one) plus that provider's IMAP host
(`EMAIL_IMAP_PORT` defaults to `993` if you don't set it).

The pipeline only ever reads **unread** mail and marks an email read after it's successfully
filed into the tree — it never deletes or modifies anything else in your inbox.

## 5. OpenRouter setup

1. Sign up at [openrouter.ai](https://openrouter.ai) and generate one or more **free-tier** API
   keys.
2. Put them in `.env`, comma-separated (more keys = more resilience against free-tier rate
   limits — the client rotates to the next key automatically):
   ```
   OPENROUTER_API_KEYS=sk-or-v1-...,sk-or-v1-...
   ```
3. `OPENROUTER_MODEL` defaults to `liquid/lfm-2.5-2.6b:free`, which worked reliably in testing.
   Free models get deprecated over time — if you see an error like "model not found" or a 404
   from OpenRouter, check [openrouter.ai/api/v1/models](https://openrouter.ai/api/v1/models)
   for a currently-valid `:free` model id and update `OPENROUTER_MODEL`.

## 6. `brain/mail_config.json`

```bash
cp brain/mail_config.example.json brain/mail_config.json
```

This file is git-ignored — it's yours, not shared. Fields:
- `seeded_categories` — top-level branches the tree starts with (edit these to match how you
  want your own mail organized).
- `student_id` / `resume_path` — only used by the placement-tracking attachment logic (matching
  your ID against an Excel selection list, matching your résumé against a JD in a PDF). Leave
  blank if you're not using that use case.

## 7. Running it

```bash
# One-off: process every unread email into the tree
uv run python -m brain.mail_ingest run

# Browse the resulting tree
uv run uvicorn brain.viz_server:app --port 8080
# then open http://127.0.0.1:8080/mail-tree
```

## 8. Known limitations

- Small free-tier models can still misclassify genuinely ambiguous mail near a category
  boundary — the BM25 keyword guardrail (`guess_category_bm25` in `brain/mail_ingest.py`)
  catches the common cases by matching keywords/company names deterministically, but it isn't
  exhaustive. Tune `category_keywords` in `DEFAULT_CONFIG` if you see recurring
  misclassifications.
- `brain.db` (the tree itself) is local and git-ignored — everyone builds their own tree from
  their own inbox; nothing about your mail content is shared via this repo.
