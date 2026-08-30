"""Resolver — the deterministic "switchboard" of the Plan B write path.

Given a candidate task (from the LLM extractor) and the set of tasks that already exist, it decides
— *deterministically* — whether the candidate is NEW, an UPDATE to an existing task, or an ambiguous
near-duplicate that needs a human to confirm. Idempotency comes from a stable key + lookup, never
from the LLM returning identical text (per the Plan B write-path design).

It is a pure function: no database, no network, no LLM. The caller (the store) applies the decision.

Matching rules, in order:
  1. The candidate carries a real source id (e.g. ClickUp id)  -> exact match on that id.
  2. No source id -> a natural key = hash(normalized name + normalized assignee).
     The natural key deliberately omits the meeting id, so the same action item mentioned across
     several meetings resolves to ONE task (cross-meeting dedup).
  3. No exact match, but a same-assignee task with a very similar name exists -> "review"
     (never silently merge; a human/Slack confirms — the Plan B grey-zone rule).
  4. Otherwise -> new task.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

# Fields that may carry an upstream id. The first present one is treated as the source key.
SOURCE_ID_FIELDS = ("source_id", "clickup_id")

# Name-similarity (0..1) at/above which a same-assignee task is flagged as a possible duplicate.
FUZZY_THRESHOLD = 0.80


@dataclass(frozen=True)
class Resolution:
    action: str           # "create" | "update" | "review"
    key: str              # the key computed for the candidate (source id or natural key)
    matched_id: str | None  # id of the existing task this matched, if any
    reason: str           # human-readable explanation of the decision


def normalize(text: str | None) -> str:
    """Lowercase, drop punctuation, collapse whitespace — so trivial wording differences match."""
    text = (text or "").lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def natural_key(name: str | None, assignee: str | None) -> str:
    """Stable key for an id-less task: hash of normalized name + assignee."""
    basis = f"{normalize(name)}|{normalize(assignee)}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _source_id(task: dict) -> str | None:
    for field in SOURCE_ID_FIELDS:
        value = task.get(field)
        if value:
            return str(value)
    return None


def resolve(candidate: dict, existing: Iterable[dict], *, fuzzy_threshold: float = FUZZY_THRESHOLD) -> Resolution:
    """Decide whether `candidate` is new, an update, or a review-needed near-duplicate."""
    existing = list(existing)

    # 1. Exact source-id match (ClickUp id, etc.) — the id IS the key.
    cid = _source_id(candidate)
    if cid:
        for e in existing:
            if _source_id(e) == cid:
                return Resolution("update", cid, e.get("id"), f"matched source id {cid}")
        return Resolution("create", cid, None, f"new task carrying source id {cid}")

    # 2. Exact natural-key match (same normalized name + assignee).
    key = natural_key(candidate.get("name"), candidate.get("assignee"))
    for e in existing:
        if _source_id(e) is None and natural_key(e.get("name"), e.get("assignee")) == key:
            return Resolution("update", key, e.get("id"), "matched natural key (name + assignee)")

    # 3. Grey zone: same assignee, very similar name -> ask a human, don't merge.
    cand_name = normalize(candidate.get("name"))
    cand_assignee = normalize(candidate.get("assignee"))
    if cand_assignee:
        best_ratio, best = 0.0, None
        for e in existing:
            if _source_id(e) is not None or normalize(e.get("assignee")) != cand_assignee:
                continue
            ratio = difflib.SequenceMatcher(None, cand_name, normalize(e.get("name"))).ratio()
            if ratio >= fuzzy_threshold and ratio > best_ratio:
                best_ratio, best = ratio, e
        if best is not None:
            return Resolution(
                "review", key, best.get("id"),
                f"possible duplicate: name {best_ratio:.0%} similar with same assignee — needs confirmation",
            )

    # 4. Genuinely new.
    return Resolution("create", key, None, "no match — new task")
