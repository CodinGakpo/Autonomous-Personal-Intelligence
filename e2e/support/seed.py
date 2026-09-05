"""Seed a user's brain database with a known mail tree for the end-to-end suite.

Gmail/IMAP is the one boundary the browser tests don't exercise (it needs a real mailbox and an
interactive OAuth consent), so instead of running ingestion we write the tree ingestion *would*
have produced. That is what makes the mail-tree and reclassify specs deterministic.

Deliberately includes a thread flagged `needs_review` and filed under the wrong category — the
yoga-competition case — so the reclassify spec has something real to correct.

    uv run python -m e2e.support.seed --user-id 1
"""

from __future__ import annotations

import argparse
import json

from brain import mail_ingest, store
from brain.emailtool import _token_path


def _mark_gmail_connected(user_id: str) -> None:
    """Make /api/mail/status report a connected mailbox.

    That endpoint only checks whether a cached token file exists, and the Mail tab hides the
    mail map entirely when Gmail is disconnected. No IMAP call is ever made in the suite, so a
    placeholder file is an honest stand-in. Playwright sets GMAIL_TOKEN_PATH into e2e/.tmp so
    this never writes to a developer's real ~/.hermes.
    """
    path = _token_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"token": "e2e-placeholder"}), encoding="utf-8")


def seed(user_id: str) -> None:
    _mark_gmail_connected(user_id)
    conn = store.connect(user_id=user_id)
    conn.execute("DELETE FROM entities")
    conn.execute("DELETE FROM edges")
    conn.commit()

    def thread(
        topic_id: str, uid: str, title: str, summary: str, body: str, *, needs_review: bool = False
    ) -> None:
        thread_id = f"mail:thread:{uid}"
        store.upsert(
            conn,
            "mail_thread",
            {
                "source_id": thread_id,
                "title": title,
                "body": body,
                "source_uids": [uid],
                "classification": {
                    "category": topic_id.split(":")[2],
                    "confidence": "low" if needs_review else "high",
                    "llm_category": "Placements" if needs_review else None,
                    "keyword_category": "General College" if needs_review else None,
                },
            },
            title=title,
            summary=summary,
            source=f"mail:{uid}",
            needs_review=needs_review,
        )
        store.add_edge(conn, topic_id, thread_id, "contains")

    accenture = mail_ingest.ensure_topic(conn, "Placements", "Accenture")
    thread(
        accenture,
        "101",
        "Accenture Off-Campus Drive 2026",
        "Off-campus drive, eligibility 7 CGPA.",
        "Eligibility criteria: 7 CGPA. CTC 6 LPA. Shortlisted students get an interview.",
    )

    # Wrongly filed under Placements, exactly as the reported bug produced. The reclassify spec
    # moves this to General College.
    yoga = mail_ingest.ensure_topic(conn, "Placements", "Yoga Competition")
    thread(
        yoga,
        "102",
        "Yoga Competition 2026",
        "Inter-department yoga competition on 12 March.",
        "The Training and Placement Cell is organising a Yoga Competition on 12 March 2026.",
        needs_review=True,
    )

    lectures = mail_ingest.ensure_topic(conn, "Lectures & Profs", "Compilers")
    thread(
        lectures,
        "103",
        "Guest Lecture on Compilers",
        "Guest lecture by a visiting professor.",
        "A guest lecture on compiler design will be held in the seminar hall.",
    )

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    args = parser.parse_args()
    seed(args.user_id)
    print(f"seeded brain for user {args.user_id}")


if __name__ == "__main__":
    main()
