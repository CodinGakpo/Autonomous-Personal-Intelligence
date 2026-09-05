"""brain/profile.py — the "About you" details, stored per user in their own brain.

These used to live only in the browser's localStorage, which meant two things: they were lost
whenever the browser was, and — more importantly — the mail pipeline could never see them.
Attachment scanning happens server-side at ingest (often from cron, with no browser anywhere),
so "is my name on this shortlist?" can only work if the answer to "what is my name?" is stored
somewhere the pipeline can read.

Free-form key/value, exactly as the Profile page presents it. Only identity-ish keys are
promoted to attachment identifiers — see IDENTITY_KEYS.
"""

from __future__ import annotations

from typing import Any

from brain import bm25, store

PROFILE_ID = "profile:me"

# Keys whose values name the person, and so are worth looking for inside an attachment.
# Deliberately an explicit list rather than "any key containing name/id": "Company name" and
# "Recruiter id" would otherwise make every shortlist look like it names you.
IDENTITY_KEYS = frozenset({
    "name", "full name", "my name", "student name",
    "roll", "roll no", "roll number",
    "register number", "registration", "registration no", "registration number",
    "reg no", "reg number",
    "neo id", "neoid",
    "student id", "employee id", "id",
    # Escape hatch for anything else you answer to; comma-separated.
    "identifier", "identifiers",
})

# Values this short are matched as whole words anyway, but a one- or two-character "identifier"
# would still fire on far too much text to be useful.
MIN_IDENTIFIER_LEN = 3


def _normalize_key(key: str) -> str:
    return " ".join(bm25.tokenize(key or ""))


def load_profile(conn: Any) -> list[dict[str, str]]:
    """This user's profile details as [{"key": ..., "value": ...}], oldest first."""
    row = store.get(conn, PROFILE_ID)
    details = (row or {}).get("data", {}).get("details") or []
    return [
        {"key": str(d.get("key", "")), "value": str(d.get("value", ""))}
        for d in details
        if isinstance(d, dict) and str(d.get("key", "")).strip()
    ]


def save_profile(conn: Any, details: list[dict[str, str]]) -> list[dict[str, str]]:
    """Replace the stored profile with `details`. Returns what was stored."""
    cleaned = [
        {"key": str(d.get("key", "")).strip(), "value": str(d.get("value", "")).strip()}
        for d in details
        if str(d.get("key", "")).strip()
    ]
    store.upsert(
        conn,
        "profile",
        {"source_id": PROFILE_ID, "title": "About you", "details": cleaned},
        title="About you",
        summary=f"{len(cleaned)} detail(s) about the user.",
        source="profile",
    )
    return cleaned


def identifiers_from_profile(details: list[dict[str, str]]) -> list[str]:
    """The profile values that count as "me" when scanning an attachment.

    A comma-separated value is split, so one "Identifiers" row can hold several.
    """
    found: list[str] = []
    for detail in details:
        if _normalize_key(detail.get("key", "")) not in IDENTITY_KEYS:
            continue
        for part in str(detail.get("value", "")).split(","):
            candidate = part.strip()
            if len(candidate) >= MIN_IDENTIFIER_LEN and candidate not in found:
                found.append(candidate)
    return found
