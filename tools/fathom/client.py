"""Fathom tool. MUST NOT import clickup or write to ClickUp directly (ADR-0001).

It returns transcript data; the agent acts on it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Transcript:
    meeting_id: str
    text: str


def fetch_transcript(meeting_id: str) -> Transcript:
    """Stub. Real Fathom API wiring lands in Track A (Plan 2)."""
    raise NotImplementedError("Implemented in Track A")
