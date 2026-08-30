#!/usr/bin/env python3
"""
brain/emailtool.py - IMAP helper for the mail knowledge-tree pipeline.

Python stdlib only (imaplib + email), so no extra pip installs are required to read mail.

Reads connection details from environment variables (the project's own `.env`, auto-loaded by
`brain/__init__.py`):
    EMAIL_EMAIL
    EMAIL_APP_PASSWORD
    EMAIL_IMAP_HOST
    EMAIL_IMAP_PORT (optional, defaults to 993)

Modes
-----
    python emailtool.py list
        Print a JSON array of unread emails to stdout. Each entry includes
        sender, subject, body text, and a list of attachments (saved to the
        cache directory as files).

    python emailtool.py mark-read <uid>
        Mark a specific email as read (\\Seen flag) by UID.

Output is a single line of JSON to stdout. Errors go to stderr and exit non-zero.
"""

import email
import email.policy
import imaplib
import json
import os
import re
import sys
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows so emojis and zero-width chars in emails
# don't crash json.dumps output with cp1252 UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ATTACHMENT_CACHE = Path(__file__).resolve().parent / ".cache" / "email-att"
ATTACHMENT_CACHE.mkdir(parents=True, exist_ok=True)


def _connect():
    user = os.environ.get("EMAIL_EMAIL")
    pw = os.environ.get("EMAIL_APP_PASSWORD")
    host = os.environ.get("EMAIL_IMAP_HOST")
    port = int(os.environ.get("EMAIL_IMAP_PORT") or 993)
    if not (user and pw and host):
        raise RuntimeError(
            "Missing EMAIL_EMAIL / EMAIL_APP_PASSWORD / EMAIL_IMAP_HOST in .env."
        )
    conn = imaplib.IMAP4_SSL(host, port)
    conn.login(user, pw)
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


def cmd_list():
    conn = _connect()
    try:
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


def main():
    if len(sys.argv) < 2:
        print("usage: emailtool.py list | mark-read <uid>", file=sys.stderr)
        sys.exit(2)
    mode = sys.argv[1]
    try:
        if mode == "list":
            cmd_list()
        elif mode == "mark-read" and len(sys.argv) >= 3:
            cmd_mark_read(sys.argv[2])
        else:
            print("usage: emailtool.py list | mark-read <uid>", file=sys.stderr)
            sys.exit(2)
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
