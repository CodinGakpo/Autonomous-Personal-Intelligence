#!/usr/bin/env python3
"""
brain/emailtool.py - IMAP helper for the mail knowledge-tree pipeline.

Fetches mail over IMAP (imaplib + email, stdlib). Two auth modes are supported:

  - App password (default, if EMAIL_APP_PASSWORD is set): plain IMAP login. See SETUP.md.
  - OAuth (if EMAIL_APP_PASSWORD is unset): XOAUTH2 over IMAP, for accounts where Google
    doesn't offer App Passwords. Needs the `google-auth` / `google-auth-oauthlib` packages.

Reads connection details from environment variables (the project's own `.env`, auto-loaded by
`brain/__init__.py`):
    EMAIL_EMAIL
    EMAIL_APP_PASSWORD          (app-password mode)
    GMAIL_CREDENTIALS_PATH      (OAuth mode, default ~/.hermes/mail/credentials.json)
    GMAIL_TOKEN_PATH            (OAuth mode, default ~/.hermes/mail/token.json)
    EMAIL_IMAP_HOST
    EMAIL_IMAP_PORT (optional, defaults to 993)

Modes
-----
    python emailtool.py list [--since-minutes N]
        Print a JSON array of unread emails to stdout. Each entry includes
        sender, subject, body text, and a list of attachments (saved to the
        cache directory as files). With --since-minutes, only unread emails
        whose Date header falls within the last N minutes are included.

    python emailtool.py mark-read <uid>
        Mark a specific email as read (\\Seen flag) by UID.

    python emailtool.py auth
        One-time interactive OAuth consent (opens a browser); caches a refresh
        token at GMAIL_TOKEN_PATH so `list` / `mark-read` never need a browser.

Output is a single line of JSON to stdout. Errors go to stderr and exit non-zero.
"""

import email
import email.policy
import email.utils
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()  # .env isn't auto-loaded here when run as a standalone script (not `-m brain...`)
except Exception:
    pass

# IMAP OAuth2 requires the full-mailbox scope — Gmail's `gmail.readonly` scope is for the
# Gmail REST API only and doesn't work over IMAP (and wouldn't let us mark messages read,
# which the pipeline needs to avoid reprocessing the same email).
GMAIL_OAUTH_SCOPES = ["https://mail.google.com/"]

# Force UTF-8 stdout/stderr on Windows so emojis and zero-width chars in emails
# don't crash json.dumps output with cp1252 UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ATTACHMENT_CACHE = Path(__file__).resolve().parent / ".cache" / "email-att"
ATTACHMENT_CACHE.mkdir(parents=True, exist_ok=True)


def _default_path(env_var: str, filename: str) -> Path:
    override = os.environ.get(env_var)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".hermes" / "mail" / filename


def _credentials_path() -> Path:
    return _default_path("GMAIL_CREDENTIALS_PATH", "credentials.json")


def _token_path() -> Path:
    return _default_path("GMAIL_TOKEN_PATH", "token.json")


def _load_oauth_credentials(interactive: bool):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = _token_path()
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_OAUTH_SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not interactive:
            raise RuntimeError(
                f"No valid OAuth token at {token_path}. Run `python emailtool.py auth` once "
                "to complete the browser consent flow."
            )
        creds_path = _credentials_path()
        if not creds_path.exists():
            raise RuntimeError(
                f"Missing OAuth client secrets at {creds_path}. Download it from Google Cloud "
                "Console (see SETUP.md) and save it there, or set GMAIL_CREDENTIALS_PATH."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), GMAIL_OAUTH_SCOPES)
        login_hint = os.environ.get("EMAIL_EMAIL")
        creds = flow.run_local_server(port=0, login_hint=login_hint)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _oauth_login(conn: imaplib.IMAP4_SSL, user: str, interactive: bool = False) -> None:
    creds = _load_oauth_credentials(interactive=interactive)
    auth_string = f"user={user}\1auth=Bearer {creds.token}\1\1"
    conn.authenticate("XOAUTH2", lambda _challenge: auth_string.encode("ascii"))


def _connect():
    user = os.environ.get("EMAIL_EMAIL")
    host = os.environ.get("EMAIL_IMAP_HOST")
    port = int(os.environ.get("EMAIL_IMAP_PORT") or 993)
    pw = os.environ.get("EMAIL_APP_PASSWORD")
    if not (user and host):
        raise RuntimeError("Missing EMAIL_EMAIL / EMAIL_IMAP_HOST in .env.")

    conn = imaplib.IMAP4_SSL(host, port)
    if pw:
        conn.login(user, pw)
    else:
        _oauth_login(conn, user)
    conn.select("INBOX")
    return conn


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name[:120] or "attachment.bin"


def _decode_part(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _extract_body(msg) -> str:
    if msg.is_multipart():
        plain_parts = []
        html_parts = []
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            if ctype == "text/plain":
                plain_parts.append(_decode_part(part))
            elif ctype == "text/html":
                html_parts.append(_decode_part(part))
        if plain_parts:
            return "\n".join(plain_parts).strip()
        # Strip tags crudely if only HTML is available
        if html_parts:
            text = "\n".join(html_parts)
            text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text
        return ""
    return _decode_part(msg).strip()


def _save_attachments(uid: str, msg):
    out = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        disp = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename()
        if "attachment" not in disp and not filename:
            continue
        if not filename:
            filename = "attachment.bin"
        safe = _safe_filename(filename)
        path = ATTACHMENT_CACHE / f"{uid}__{safe}"
        try:
            data = part.get_payload(decode=True)
            if data:
                path.write_bytes(data)
                out.append(
                    {
                        "filename": filename,
                        "content_type": part.get_content_type(),
                        "saved_to": str(path),
                        "size_bytes": len(data),
                    }
                )
        except Exception as e:
            out.append({"filename": filename, "error": str(e)})
    return out


def cmd_list(since_minutes: int | None = None):
    cutoff = None
    if since_minutes is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)

    conn = _connect()
    try:
        # IMAP SINCE only has day granularity, so it's a coarse prefilter (avoids fetching a
        # whole old unread backlog) — the precise per-message Date check below does the rest.
        if cutoff is not None:
            since_date = cutoff.strftime("%d-%b-%Y")
            typ, data = conn.uid("search", None, f'(UNSEEN SINCE "{since_date}")')
        else:
            typ, data = conn.uid("search", None, "UNSEEN")
        if typ != "OK":
            raise RuntimeError(f"IMAP search failed: {typ} {data}")
        uids = data[0].split()
        results = []
        for uid_bytes in uids:
            uid = uid_bytes.decode("ascii")
            typ, msg_data = conn.uid("fetch", uid_bytes, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            if cutoff is not None:
                try:
                    msg_date = email.utils.parsedate_to_datetime(str(msg.get("Date", "")))
                    if msg_date.tzinfo is None:
                        msg_date = msg_date.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    continue
                if msg_date < cutoff:
                    continue
            results.append(
                {
                    "uid": uid,
                    "from": str(msg.get("From", "")),
                    "to": str(msg.get("To", "")),
                    "subject": str(msg.get("Subject", "")),
                    "date": str(msg.get("Date", "")),
                    "body_text": _extract_body(msg),
                    "attachments": _save_attachments(uid, msg),
                }
            )
        print(json.dumps(results, ensure_ascii=False))
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def cmd_mark_read(uid: str):
    conn = _connect()
    try:
        typ, _ = conn.uid("store", uid.encode("ascii"), "+FLAGS", "(\\Seen)")
        if typ != "OK":
            raise RuntimeError(f"IMAP STORE failed for uid {uid}: {typ}")
        print(json.dumps({"uid": uid, "marked_read": True}))
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def cmd_auth():
    user = os.environ.get("EMAIL_EMAIL")
    if not user:
        raise RuntimeError("Missing EMAIL_EMAIL in .env.")
    _load_oauth_credentials(interactive=True)
    print(json.dumps({"authenticated": user, "token_path": str(_token_path())}))


def main():
    usage = "usage: emailtool.py list [--since-minutes N] | mark-read <uid> | auth"
    if len(sys.argv) < 2:
        print(usage, file=sys.stderr)
        sys.exit(2)
    mode = sys.argv[1]
    try:
        if mode == "list":
            since_minutes = None
            if "--since-minutes" in sys.argv:
                idx = sys.argv.index("--since-minutes")
                if idx + 1 >= len(sys.argv):
                    print(usage, file=sys.stderr)
                    sys.exit(2)
                since_minutes = int(sys.argv[idx + 1])
            cmd_list(since_minutes)
        elif mode == "mark-read" and len(sys.argv) >= 3:
            cmd_mark_read(sys.argv[2])
        elif mode == "auth":
            cmd_auth()
        else:
            print(usage, file=sys.stderr)
            sys.exit(2)
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
