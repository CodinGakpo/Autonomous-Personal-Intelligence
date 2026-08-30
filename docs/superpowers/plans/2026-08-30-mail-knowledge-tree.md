# Mail Knowledge Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn unread mail into a standing, browsable knowledge tree inside the existing brain — an LLM classifies each email into a category/topic and either merges it into an existing thread node or creates a new one, so related mail (e.g. a company's interview → PPT → OA rounds) reads as one coherent picture instead of scattered messages.

**Architecture:** A new `brain/mail_ingest.py` orchestrates: fetch unread mail via the already-working `emailtool.py` IMAP helper → extract attachment content locally (Excel row match, capped PDF text) → two small OpenRouter LLM calls (classify, then merge-or-create) → write via the brain's existing `store.upsert`/`store.add_edge` (three new entity types, two new edge relations) → mark the email read only after a successful write. A new `brain/openrouter.py` gives the mail pipeline an HTTP LLM call with automatic key rotation across multiple free-tier keys.

**Tech Stack:** Python 3.11, `requests` (already a dependency) for OpenRouter HTTP calls, `openpyxl` (new dependency) for Excel parsing, `pypdf` (already a dependency) for PDF text, `pytest` + `responses` (already a dev dependency) for tests, SQLite via the existing `brain/store.py`.

## Global Constraints

- Python >= 3.11 (`pyproject.toml`'s `requires-python`).
- Ruff line-length 100, lint rules `["E", "F", "I", "UP", "B"]` — match existing style in `brain/`.
- Reuse `brain/store.py`'s `upsert`/`add_edge`/`all_of_type`/`get`/`neighbors` and `brain/resolver.py` unchanged — no schema or resolver changes. Idempotency is achieved entirely by always supplying a deterministic `source_id` in every candidate dict (the resolver's exact-match path).
- `.env` is auto-loaded by `brain/__init__.py` (via `python-dotenv`) — no manual dotenv loading needed in new modules.
- No Hermes involvement in the ingest pipeline itself — plain Python, runnable via cron or manually (per explicit user preference).
- `OPENROUTER_API_KEYS` (comma-separated) and `OPENROUTER_MODEL` are already set in the repo's local `.env` (git-ignored); default model is `meta-llama/llama-3.1-8b-instruct:free`.
- Follow the spec at `docs/superpowers/specs/2026-08-30-mail-knowledge-tree-design.md` for all node/edge naming and behavior.

---

## Task 1: OpenRouter client with free-tier key rotation

**Files:**
- Create: `brain/openrouter.py`
- Test: `tests/test_openrouter.py`

**Interfaces:**
- Produces: `call_openrouter(prompt: str, *, model: str | None = None) -> str` — sends `prompt` as a single user message, returns the model's text reply, rotates across `OPENROUTER_API_KEYS` on 401/402/429, raises `SystemExit` if all keys are exhausted or no keys are configured.
- Produces: `openrouter.OPENROUTER_URL` (module constant, used by tests to register mock routes).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_openrouter.py`:

```python
"""Tests for the mail pipeline's OpenRouter client and free-tier key rotation."""

import pytest
import responses

from brain import openrouter


def _set_keys(monkeypatch, keys="k1,k2", model="test-model"):
    monkeypatch.setenv("OPENROUTER_API_KEYS", keys)
    monkeypatch.setenv("OPENROUTER_MODEL", model)


@responses.activate
def test_call_openrouter_returns_content(monkeypatch):
    _set_keys(monkeypatch, keys="k1")
    responses.add(
        responses.POST, openrouter.OPENROUTER_URL,
        json={"choices": [{"message": {"content": "hello"}}]}, status=200,
    )
    assert openrouter.call_openrouter("hi") == "hello"


@responses.activate
def test_call_openrouter_rotates_on_429(monkeypatch):
    _set_keys(monkeypatch, keys="bad,good")
    responses.add(responses.POST, openrouter.OPENROUTER_URL, status=429)
    responses.add(
        responses.POST, openrouter.OPENROUTER_URL,
        json={"choices": [{"message": {"content": "ok"}}]}, status=200,
    )
    assert openrouter.call_openrouter("hi") == "ok"
    assert len(responses.calls) == 2
    assert responses.calls[0].request.headers["Authorization"] == "Bearer bad"
    assert responses.calls[1].request.headers["Authorization"] == "Bearer good"


@responses.activate
def test_call_openrouter_all_keys_exhausted_raises(monkeypatch):
    _set_keys(monkeypatch, keys="k1,k2")
    responses.add(responses.POST, openrouter.OPENROUTER_URL, status=429)
    responses.add(responses.POST, openrouter.OPENROUTER_URL, status=429)
    with pytest.raises(SystemExit):
        openrouter.call_openrouter("hi")


def test_call_openrouter_missing_keys_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEYS", raising=False)
    with pytest.raises(SystemExit):
        openrouter.call_openrouter("hi")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_openrouter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.openrouter'`

- [ ] **Step 3: Write the implementation**

Create `brain/openrouter.py`:

```python
"""brain/openrouter.py — the mail pipeline's LLM seam: OpenRouter with free-tier key rotation.

Separate from brain/engine.py (which shells out to a local CLI). The mail pipeline needs a real
HTTP LLM call, and needs to survive a single free-tier key running dry mid-run — so this module
tries each key in OPENROUTER_API_KEYS in order and rotates forward on a 401/402/429 response.
"""

from __future__ import annotations

import os

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
TIMEOUT_S = 120

# Status codes that mean "this key is done" — rotate to the next one rather than failing outright.
ROTATE_ON = {401, 402, 429}


def _keys() -> list[str]:
    raw = os.environ.get("OPENROUTER_API_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise SystemExit("Set OPENROUTER_API_KEYS (comma-separated) in .env to use the mail pipeline.")
    return keys


def call_openrouter(prompt: str, *, model: str | None = None) -> str:
    """Send `prompt` as a single user message; return the model's text reply.

    Tries each key in OPENROUTER_API_KEYS in turn, rotating forward whenever a key is
    rejected or rate/quota-limited (401/402/429), so one exhausted free-tier key doesn't
    stop the run.
    """
    model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    keys = _keys()
    last_error = ""

    for key in keys:
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                timeout=TIMEOUT_S,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            continue

        if response.status_code in ROTATE_ON:
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            continue

        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    raise SystemExit(f"All OPENROUTER_API_KEYS exhausted or rejected. Last error: {last_error}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_openrouter.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add brain/openrouter.py tests/test_openrouter.py
git commit -m "feat(brain): OpenRouter client with free-tier key rotation"
```

---

## Task 2: Local-first attachment handling (Excel ID match, capped PDF, résumé-vs-JD)

**Files:**
- Modify: `pyproject.toml` (add `openpyxl` dependency)
- Create: `brain/mail_attachments.py`
- Test: `tests/test_mail_attachments.py`

**Interfaces:**
- Consumes: `brain.openrouter.call_openrouter(prompt: str, *, model: str | None = None) -> str` (Task 1).
- Produces: `process_attachment(path: Path, config: dict) -> dict` — returns `{"file": str, "kind": str, "finding": ...}`; `kind` is one of `"excel"`, `"pdf"`, `"pdf_jd"`, or the file's lowercase suffix (e.g. `"docx"`) for anything unhandled. Used by Task 3's `mail_ingest.py`.
- Produces: `extract_excel_match`, `extract_pdf_text`, `looks_like_job_description`, `match_resume_to_jd` (each independently testable, used internally by `process_attachment`).

- [ ] **Step 1: Add the openpyxl dependency**

Edit `pyproject.toml`, in the `[project]` `dependencies` list, add `"openpyxl>=3.1"` after the `"pypdf>=6.14.2",` line:

```toml
    "pypdf>=6.14.2",
    "openpyxl>=3.1",
```

Run: `uv sync`
Expected: `openpyxl` installed, `uv.lock` updated.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_mail_attachments.py`:

```python
"""Tests for the mail pipeline's local-first attachment handling (Excel/PDF)."""

from pathlib import Path

import pytest

from brain import mail_attachments as ma


def _make_excel(tmp_path, headers, rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    path = tmp_path / "sheet.xlsx"
    wb.save(str(path))
    return path


def test_extract_excel_match_finds_row(tmp_path):
    path = _make_excel(
        tmp_path, ["Name", "Student ID", "Status"],
        [["Asha", "S123", "Selected"], ["Ravi", "S456", "Not Selected"]],
    )
    result = ma.extract_excel_match(path, "S456")
    assert result == {"headers": ["Name", "Student ID", "Status"], "row": ["Ravi", "S456", "Not Selected"]}


def test_extract_excel_match_no_match_returns_none(tmp_path):
    path = _make_excel(tmp_path, ["Name", "Student ID"], [["Asha", "S123"]])
    assert ma.extract_excel_match(path, "S999") is None


def test_extract_excel_match_no_id_column_returns_none(tmp_path):
    path = _make_excel(tmp_path, ["Name", "Score"], [["Asha", "90"]])
    assert ma.extract_excel_match(path, "S123") is None


def test_looks_like_job_description_true_for_jd_text():
    text = "Responsibilities: build stuff. Requirements: Python. Qualifications: CS degree."
    assert ma.looks_like_job_description(text)


def test_looks_like_job_description_false_for_plain_text():
    assert not ma.looks_like_job_description("Hey, lunch at noon?")


def test_extract_pdf_text_caps_length(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "x" * 10000

    class FakeReader:
        def __init__(self, _path):
            self.pages = [FakePage()]

    monkeypatch.setattr("pypdf.PdfReader", FakeReader)
    text = ma.extract_pdf_text(Path("fake.pdf"), max_chars=100)
    assert len(text) == 100


def test_match_resume_to_jd_calls_openrouter(monkeypatch):
    captured = {}

    def fake_call(prompt):
        captured["prompt"] = prompt
        return "Good match on Python."

    monkeypatch.setattr(ma, "call_openrouter", fake_call)
    note = ma.match_resume_to_jd("Need Python dev", {"skills": ["Python"], "summary": "backend eng"})
    assert note == "Good match on Python."
    assert "Python" in captured["prompt"]


def test_process_attachment_excel_dispatch(tmp_path):
    path = _make_excel(tmp_path, ["Name", "Student ID"], [["Asha", "S1"]])
    result = ma.process_attachment(path, {"student_id": "S1"})
    assert result["kind"] == "excel"
    assert result["finding"] == {"Name": "Asha", "Student ID": "S1"}


def test_process_attachment_unsupported_type(tmp_path):
    path = tmp_path / "notes.docx"
    path.write_text("hi")
    result = ma.process_attachment(path, {})
    assert result["finding"] == "attachment not parsed"


def test_process_attachment_pdf_non_jd(tmp_path, monkeypatch):
    monkeypatch.setattr(ma, "extract_pdf_text", lambda path, max_chars=ma.PDF_CHAR_CAP: "Hey, see you soon.")
    path = tmp_path / "note.pdf"
    path.write_bytes(b"%PDF-1.4")
    result = ma.process_attachment(path, {})
    assert result["kind"] == "pdf"


def test_process_attachment_pdf_jd_with_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ma, "extract_pdf_text",
        lambda path, max_chars=ma.PDF_CHAR_CAP: "Responsibilities: code. Requirements: Python. Qualifications: BS.",
    )
    monkeypatch.setattr(ma, "match_resume_to_jd", lambda jd, profile: "matches well")
    path = tmp_path / "jd.pdf"
    path.write_bytes(b"%PDF-1.4")
    result = ma.process_attachment(path, {"resume_profile": {"skills": ["Python"]}})
    assert result == {"file": "jd.pdf", "kind": "pdf_jd", "finding": "matches well"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_mail_attachments.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.mail_attachments'`

- [ ] **Step 4: Write the implementation**

Create `brain/mail_attachments.py`:

```python
"""brain/mail_attachments.py — local-first attachment handling for the mail pipeline.

Excel: parsed entirely locally (no LLM) — find the row matching the student's own id.
PDF: text extracted locally, hard-capped, then (only if it looks like a JD) compared to the
student's résumé profile via one small LLM call.

The local-first, hard-capped design is the guard against a single large attachment burning
through a free-tier OpenRouter key on one email.
"""

from __future__ import annotations

from pathlib import Path

from brain.openrouter import call_openrouter

PDF_CHAR_CAP = 4000
EXCEL_SUFFIXES = {".xlsx", ".xls"}
JD_KEYWORDS = (
    "responsibilities", "requirements", "qualifications",
    "job description", "role overview", "skills required",
)


def extract_excel_match(path: Path, student_id: str) -> dict | None:
    """Find the row whose ID-like column matches `student_id`. None if no match or no ID column."""
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return None
    headers = [str(h) if h is not None else "" for h in rows[0]]
    id_col = next((i for i, h in enumerate(headers) if "id" in h.lower()), None)
    if id_col is None:
        return None
    for row in rows[1:]:
        cell = row[id_col]
        if cell is not None and str(cell).strip() == str(student_id).strip():
            return {"headers": headers, "row": [str(c) if c is not None else "" for c in row]}
    return None


def extract_pdf_text(path: Path, max_chars: int = PDF_CHAR_CAP) -> str:
    """Extract PDF text via pypdf, hard-capped at `max_chars`."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text[:max_chars]


def looks_like_job_description(text: str) -> bool:
    """Cheap local heuristic — no LLM call needed just to decide whether to bother matching."""
    lowered = text.lower()
    return sum(1 for kw in JD_KEYWORDS if kw in lowered) >= 2


def match_resume_to_jd(jd_text: str, resume_profile: dict) -> str:
    """One small LLM call: does this student's résumé match this JD? Short match/gap note."""
    skills = ", ".join(resume_profile.get("skills", []))
    prompt = (
        "You are screening ONE candidate against ONE job description. Reply with 2-3 short "
        "sentences: how well they match, and the clearest gap if any. No preamble, no markdown.\n\n"
        f"CANDIDATE SKILLS: {skills}\n"
        f"CANDIDATE SUMMARY: {resume_profile.get('summary') or resume_profile.get('headline') or ''}\n\n"
        f"JOB DESCRIPTION:\n{jd_text}"
    )
    return call_openrouter(prompt).strip()


def process_attachment(path: Path, config: dict) -> dict:
    """Dispatch one saved attachment file by suffix. Always returns a small, prompt-safe finding."""
    suffix = Path(path).suffix.lower()

    if suffix in EXCEL_SUFFIXES:
        match = extract_excel_match(path, config.get("student_id", ""))
        if match is None:
            return {"file": Path(path).name, "kind": "excel", "finding": "no matching row for student id"}
        return {"file": Path(path).name, "kind": "excel", "finding": dict(zip(match["headers"], match["row"]))}

    if suffix == ".pdf":
        text = extract_pdf_text(path)
        if not looks_like_job_description(text):
            return {"file": Path(path).name, "kind": "pdf", "finding": text[:500]}
        resume_profile = config.get("resume_profile") or {}
        note = match_resume_to_jd(text, resume_profile) if resume_profile else "no résumé configured to match against"
        return {"file": Path(path).name, "kind": "pdf_jd", "finding": note}

    return {"file": Path(path).name, "kind": suffix.lstrip(".") or "unknown", "finding": "attachment not parsed"}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_mail_attachments.py -v`
Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock brain/mail_attachments.py tests/test_mail_attachments.py
git commit -m "feat(brain): local-first Excel/PDF attachment handling for the mail pipeline"
```

---

## Task 3: Mail config + classify/merge LLM calls

**Files:**
- Create: `brain/mail_ingest.py` (this task writes the config + classify/merge portion; Task 4 and Task 5 extend the same file)
- Test: `tests/test_mail_ingest.py`

**Interfaces:**
- Consumes: `brain.openrouter.call_openrouter` (Task 1).
- Produces: `load_config(path: Path = CONFIG_PATH) -> dict` — merges `brain/mail_config.json` over `DEFAULT_CONFIG`.
- Produces: `_slugify(text: str) -> str` — used by Task 4 to build deterministic node ids.
- Produces: `classify_email(email: dict, attachment_findings: list[dict], categories: list[dict]) -> dict` — returns `{"category": str, "new_category": bool, "topic": str, "new_topic": bool}`. Used by Task 4.
- Produces: `merge_or_create_thread(email: dict, attachment_findings: list[dict], existing_threads: list[dict]) -> dict` — returns `{"action": "merge"|"new", "merge_into_id": str|None, "summary": str, "body": str}`. Used by Task 4.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mail_ingest.py`:

```python
"""Tests for the mail knowledge-tree pipeline: config, and classify/merge LLM-call parsing."""

import json

from brain import mail_ingest


def test_load_config_defaults_when_missing(tmp_path):
    cfg = mail_ingest.load_config(tmp_path / "nope.json")
    assert cfg["seeded_categories"] == ["Placements", "Banking", "Academics", "Job Hunt"]
    assert cfg["student_id"] == ""


def test_load_config_merges_file_over_defaults(tmp_path):
    path = tmp_path / "mail_config.json"
    path.write_text(json.dumps({"student_id": "S1"}), encoding="utf-8")
    cfg = mail_ingest.load_config(path)
    assert cfg["student_id"] == "S1"
    assert cfg["seeded_categories"] == ["Placements", "Banking", "Academics", "Job Hunt"]


def test_slugify():
    assert mail_ingest._slugify("Acme Corp!") == "acme-corp"
    assert mail_ingest._slugify("") == "untitled"


def test_classify_email_parses_llm_json(monkeypatch):
    monkeypatch.setattr(
        mail_ingest, "call_openrouter",
        lambda prompt: '{"category": "Placements", "new_category": false, "topic": "Acme", "new_topic": true}',
    )
    result = mail_ingest.classify_email(
        {"from": "a@x.com", "subject": "Interview", "body_text": "..."}, [], [],
    )
    assert result == {"category": "Placements", "new_category": False, "topic": "Acme", "new_topic": True}


def test_classify_email_strips_markdown_fences(monkeypatch):
    monkeypatch.setattr(
        mail_ingest, "call_openrouter",
        lambda prompt: '```json\n{"category": "Placements", "new_category": false, "topic": "Acme", "new_topic": false}\n```',
    )
    result = mail_ingest.classify_email({"from": "a", "subject": "s", "body_text": "b"}, [], [])
    assert result["category"] == "Placements"


def test_merge_or_create_thread_parses_llm_json(monkeypatch):
    monkeypatch.setattr(
        mail_ingest, "call_openrouter",
        lambda prompt: '{"action": "new", "merge_into_id": null, "summary": "s", "body": "b"}',
    )
    result = mail_ingest.merge_or_create_thread(
        {"from": "a", "subject": "s", "body_text": "b"}, [], [],
    )
    assert result["action"] == "new"
    assert result["body"] == "b"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mail_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brain.mail_ingest'`

- [ ] **Step 3: Write the implementation**

Create `brain/mail_ingest.py`:

```python
"""brain/mail_ingest.py — the mail knowledge-tree pipeline.

    emailtool.py list ─▶ attachment handling ─▶ classify (LLM) ─▶ merge/place (LLM) ─▶ store upsert ─▶ mark-read

Builds three new node types in the existing brain (brain/store.py's entities/edges):

    mail_category ──contains──▶ mail_topic ──contains──▶ mail_thread

Plain Python, no Hermes — run manually or from a scheduled task. See
docs/superpowers/specs/2026-08-30-mail-knowledge-tree-design.md for the design.

Usage:
    uv run python -m brain.mail_ingest run
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from brain.openrouter import call_openrouter

CONFIG_PATH = Path(__file__).resolve().parent / "mail_config.json"

DEFAULT_CONFIG = {
    "student_id": "",
    "resume_path": "",
    "seeded_categories": ["Placements", "Banking", "Academics", "Job Hunt"],
}


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Read brain/mail_config.json, filling in defaults for anything missing."""
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    data = json.loads(path.read_text(encoding="utf-8"))
    return {**DEFAULT_CONFIG, **data}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "untitled"


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def classify_email(
    email: dict[str, Any], attachment_findings: list[dict[str, Any]], categories: list[dict[str, Any]]
) -> dict[str, Any]:
    """LLM call: which category + topic does this email belong to (existing or new)?"""
    cat_lines = "\n".join(f"- {c['title']}: {c.get('summary', '')}" for c in categories) or "(none yet)"
    findings_text = "\n".join(
        f"- {f['file']} ({f['kind']}): {f['finding']}" for f in attachment_findings
    ) or "(none)"
    prompt = (
        "You file one email into a knowledge tree. Pick the best-fitting CATEGORY (a broad area) "
        "and, within it, the best-fitting TOPIC (a specific thing, e.g. a company name or account). "
        "Prefer an existing category/topic; only propose a new one when nothing existing fits.\n\n"
        f"EXISTING CATEGORIES:\n{cat_lines}\n\n"
        f"EMAIL\nFrom: {email.get('from')}\nSubject: {email.get('subject')}\n"
        f"Body: {email.get('body_text', '')[:2000]}\n"
        f"Attachment findings:\n{findings_text}\n\n"
        'Reply with ONLY this JSON object, nothing else:\n'
        '{"category": "<name>", "new_category": true|false, "topic": "<name>", "new_topic": true|false}'
    )
    raw = _strip_fences(call_openrouter(prompt))
    return json.loads(raw)


def merge_or_create_thread(
    email: dict[str, Any],
    attachment_findings: list[dict[str, Any]],
    existing_threads: list[dict[str, Any]],
) -> dict[str, Any]:
    """LLM call: merge into an existing thread node, or create a new one."""
    thread_lines = "\n".join(
        f"- id={t['id']}: {t.get('summary', '')}" for t in existing_threads
    ) or "(none yet)"
    findings_text = "\n".join(
        f"- {f['file']} ({f['kind']}): {f['finding']}" for f in attachment_findings
    ) or "(none)"
    prompt = (
        "You maintain a knowledge node for one topic. Given a new email and the topic's existing "
        "nodes (id + summary), decide whether this email is closely related enough to merge into one "
        "of them (e.g. another round of the same process: interview, PPT, OA, result) or is "
        "unrelated enough to start a new node.\n\n"
        "If merging, write an updated body that folds the new information into the existing one "
        "coherently (a running picture, not a raw concatenation) and a fresh short summary.\n"
        "If new, write a body and summary for just this email.\n\n"
        f"EXISTING NODES IN THIS TOPIC:\n{thread_lines}\n\n"
        f"NEW EMAIL\nFrom: {email.get('from')}\nSubject: {email.get('subject')}\n"
        f"Body: {email.get('body_text', '')[:2000]}\n"
        f"Attachment findings:\n{findings_text}\n\n"
        'Reply with ONLY this JSON object, nothing else:\n'
        '{"action": "merge"|"new", "merge_into_id": "<id or null>", '
        '"summary": "<routing digest, <=120 words>", "body": "<full content>"}'
    )
    raw = _strip_fences(call_openrouter(prompt))
    return json.loads(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mail_ingest.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add brain/mail_ingest.py tests/test_mail_ingest.py
git commit -m "feat(brain): mail config + classify/merge LLM calls for the mail pipeline"
```

---

## Task 4: Per-email store write path (`ingest_email`)

**Files:**
- Modify: `brain/mail_ingest.py` (append to the file created in Task 3)
- Modify: `tests/test_mail_ingest.py` (append)

**Interfaces:**
- Consumes: `brain.store.upsert`, `store.add_edge`, `store.all_of_type`, `store.get`, `store.neighbors`, `store.connect` (existing, unchanged).
- Consumes: `brain.mail_attachments.process_attachment` (Task 2).
- Consumes: `classify_email`, `merge_or_create_thread`, `_slugify` (Task 3, same file).
- Produces: `gather_attachment_findings(email: dict, config: dict) -> list[dict]` — used by `ingest_email` and by Task 5's `run`.
- Produces: `ingest_email(conn, email: dict, config: dict) -> dict` — returns `{"uid": str, "category": str, "topic": str, "thread_id": str, "action": "merge"|"new"}`. Used by Task 5's `run`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mail_ingest.py`:

```python
from brain import store


def _conn(tmp_path):
    return store.connect(tmp_path / "t.db")


def _email(uid="1", subject="Interview Round 1"):
    return {
        "uid": uid, "from": "hr@acme.com", "to": "me@x.com", "subject": subject,
        "body_text": "...", "attachments": [],
    }


def test_ingest_email_creates_category_topic_and_thread(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(
        mail_ingest, "classify_email",
        lambda email, findings, categories: {
            "category": "Placements", "new_category": True, "topic": "Acme", "new_topic": True,
        },
    )
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "new", "merge_into_id": None,
            "summary": "Interview scheduled.", "body": "Round 1 interview on Monday.",
        },
    )
    result = mail_ingest.ingest_email(conn, _email(), {"student_id": "", "resume_path": ""})

    assert result["category"] == "Placements"
    assert result["topic"] == "Acme"
    assert store.get(conn, "mail:cat:placements")["title"] == "Placements"
    assert store.get(conn, "mail:topic:placements:acme")["title"] == "Acme"
    thread = store.get(conn, result["thread_id"])
    assert thread["data"]["body"] == "Round 1 interview on Monday."
    assert thread["data"]["source_uids"] == ["1"]


def test_ingest_email_merges_second_related_email_into_same_thread(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(
        mail_ingest, "classify_email",
        lambda email, findings, categories: {
            "category": "Placements", "new_category": True, "topic": "Acme", "new_topic": True,
        },
    )
    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "new", "merge_into_id": None,
            "summary": "Interview scheduled.", "body": "Round 1 interview.",
        },
    )
    first = mail_ingest.ingest_email(conn, _email(uid="1"), {"student_id": "", "resume_path": ""})

    monkeypatch.setattr(
        mail_ingest, "merge_or_create_thread",
        lambda email, findings, existing: {
            "action": "merge", "merge_into_id": first["thread_id"],
            "summary": "Interview + PPT scheduled.",
            "body": "Round 1 interview.\nPPT on Wednesday.",
        },
    )
    second = mail_ingest.ingest_email(conn, _email(uid="2", subject="PPT"), {"student_id": "", "resume_path": ""})

    assert second["thread_id"] == first["thread_id"]
    thread = store.get(conn, second["thread_id"])
    assert thread["data"]["body"] == "Round 1 interview.\nPPT on Wednesday."
    assert sorted(thread["data"]["source_uids"]) == ["1", "2"]
    assert len(store.all_of_type(conn, "mail_thread")) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mail_ingest.py -v -k ingest_email`
Expected: FAIL with `AttributeError: module 'brain.mail_ingest' has no attribute 'ingest_email'`

- [ ] **Step 3: Write the implementation**

Append to `brain/mail_ingest.py` (add these imports to the existing `from __future__ import annotations` block at the top, alongside the existing imports):

```python
from brain import store
from brain.mail_attachments import process_attachment
```

Then append these functions at the end of the file:

```python
def gather_attachment_findings(email: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for att in email.get("attachments", []):
        saved_to = att.get("saved_to")
        if not saved_to:
            continue
        findings.append(process_attachment(Path(saved_to), config))
    return findings


def ingest_email(conn: Any, email: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Full per-email pipeline: attachments -> classify -> merge/place -> store. No mark-read here."""
    findings = gather_attachment_findings(email, config)

    categories = store.all_of_type(conn, "mail_category")
    classification = classify_email(email, findings, categories)

    cat_title = classification["category"]
    cat_id = f"mail:cat:{_slugify(cat_title)}"
    store.upsert(
        conn, "mail_category", {"source_id": cat_id, "title": cat_title},
        title=cat_title, summary=f"Mail about {cat_title}.", source="mail",
    )

    topic_title = classification["topic"]
    topic_id = f"mail:topic:{_slugify(cat_title)}:{_slugify(topic_title)}"
    existing_topic = store.get(conn, topic_id)
    store.upsert(
        conn, "mail_topic", {"source_id": topic_id, "title": topic_title},
        title=topic_title,
        summary=existing_topic["summary"] if existing_topic else f"Mail about {topic_title}.",
        source="mail",
    )
    store.add_edge(conn, cat_id, topic_id, "contains")

    existing_threads = [
        t for t in store.all_of_type(conn, "mail_thread")
        if any(n["id"] == topic_id for n in store.neighbors(conn, t["id"], "contains", incoming=True))
    ]
    decision = merge_or_create_thread(email, findings, existing_threads)

    if decision["action"] == "merge" and decision.get("merge_into_id"):
        thread_id = decision["merge_into_id"]
        existing_thread = store.get(conn, thread_id)
        prior_uids = existing_thread["data"].get("source_uids", []) if existing_thread else []
        uids = sorted({*prior_uids, email["uid"]})
    else:
        thread_id = f"mail:thread:{email['uid']}"
        uids = [email["uid"]]

    store.upsert(
        conn, "mail_thread",
        {
            "source_id": thread_id, "title": email.get("subject", ""),
            "body": decision["body"], "source_uids": uids,
        },
        title=email.get("subject", ""), summary=decision["summary"], source=f"mail:{email['uid']}",
    )
    store.add_edge(conn, topic_id, thread_id, "contains")

    return {
        "uid": email["uid"], "category": cat_title, "topic": topic_title,
        "thread_id": thread_id, "action": decision["action"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mail_ingest.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add brain/mail_ingest.py tests/test_mail_ingest.py
git commit -m "feat(brain): per-email store write path (ingest_email) for the mail pipeline"
```

---

## Task 5: Fetch, mark-read, run(), CLI, and the config file

**Files:**
- Modify: `brain/mail_ingest.py` (append to the file from Tasks 3-4)
- Modify: `tests/test_mail_ingest.py` (append)
- Create: `brain/mail_config.json`

**Interfaces:**
- Consumes: `ingest_email`, `load_config` (Tasks 3-4, same file).
- Produces: `fetch_unread_emails() -> list[dict]` — runs `emailtool.py list`, parses its JSON output.
- Produces: `mark_email_read(uid: str) -> None` — runs `emailtool.py mark-read <uid>`.
- Produces: `run(conn: Any = None) -> list[dict]` — the full batch: fetch, ingest each, mark read only on success. Each result is either an `ingest_email` result or `{"uid": ..., "error": str}`.
- Produces: CLI entry point `python -m brain.mail_ingest run`.

- [ ] **Step 1: Create the config file**

Create `brain/mail_config.json`:

```json
{
  "student_id": "",
  "resume_path": "",
  "seeded_categories": ["Placements", "Banking", "Academics", "Job Hunt"]
}
```

Fill in `student_id` (the ID that appears in placement-result spreadsheets) and `resume_path`
(a path to a résumé file, parseable by `tools/resume/parser.py`) before running this for real.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_mail_ingest.py`:

```python
def test_run_marks_read_only_on_success(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    monkeypatch.setattr(
        mail_ingest, "fetch_unread_emails",
        lambda: [_email(uid="1"), _email(uid="2", subject="bad")],
    )

    def fake_ingest(conn_, email, config):
        if email["uid"] == "2":
            raise ValueError("boom")
        return {
            "uid": email["uid"], "category": "C", "topic": "T",
            "thread_id": "mail:thread:1", "action": "new",
        }

    monkeypatch.setattr(mail_ingest, "ingest_email", fake_ingest)
    marked = []
    monkeypatch.setattr(mail_ingest, "mark_email_read", lambda uid: marked.append(uid))
    monkeypatch.setattr(mail_ingest, "load_config", lambda: {"student_id": "", "resume_path": ""})

    results = mail_ingest.run(conn)

    assert marked == ["1"]
    assert results[0]["uid"] == "1"
    assert results[1]["error"] == "boom"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_mail_ingest.py -v -k test_run_marks_read_only_on_success`
Expected: FAIL with `AttributeError: module 'brain.mail_ingest' has no attribute 'fetch_unread_emails'`

- [ ] **Step 4: Write the implementation**

Add these imports to the top of `brain/mail_ingest.py` (alongside the existing ones):

```python
import subprocess
import sys
```

Append at the end of `brain/mail_ingest.py`:

```python
EMAILTOOL = (
    Path.home() / ".hermes" / "skills" / "automation" / "placement-email-processor"
    / "scripts" / "emailtool.py"
)


def fetch_unread_emails() -> list[dict[str, Any]]:
    """Run emailtool.py list; return the parsed unread-email list."""
    proc = subprocess.run(
        [sys.executable, str(EMAILTOOL), "list"],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    if proc.returncode != 0:
        raise SystemExit(f"emailtool.py list failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def mark_email_read(uid: str) -> None:
    """Run emailtool.py mark-read <uid>."""
    proc = subprocess.run(
        [sys.executable, str(EMAILTOOL), "mark-read", uid],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    if proc.returncode != 0:
        raise SystemExit(f"emailtool.py mark-read failed: {proc.stderr.strip()}")


def run(conn: Any = None) -> list[dict[str, Any]]:
    """Fetch unread mail, ingest each into the tree, mark read only on success."""
    conn = conn or store.connect()
    config = load_config()
    if config.get("resume_path"):
        from tools.resume.parser import parse_resume

        config["resume_profile"] = parse_resume(Path(config["resume_path"]))

    results = []
    for email in fetch_unread_emails():
        try:
            result = ingest_email(conn, email, config)
        except Exception as exc:  # one bad email must not stop the whole run
            results.append({"uid": email.get("uid"), "error": str(exc)})
            continue
        mark_email_read(email["uid"])
        results.append(result)
    return results


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] != "run":
        print("usage: python -m brain.mail_ingest run", file=sys.stderr)
        sys.exit(2)
    for result in run():
        if "error" in result:
            print(f"[error] uid {result['uid']}: {result['error']}")
        else:
            print(f"[{result['action']}] {result['category']} / {result['topic']} -> {result['thread_id']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_mail_ingest.py tests/test_mail_attachments.py tests/test_openrouter.py -v`
Expected: all pass (9 in test_mail_ingest.py, 10 in test_mail_attachments.py, 4 in test_openrouter.py)

- [ ] **Step 6: Manual end-to-end smoke test (uses real IMAP + real OpenRouter — costs a small amount of free-tier quota)**

Run: `uv run python -m brain.mail_ingest run`
Expected: prints one `[new]` or `[merge]` line per unread email (or `[error]` with a reason), and re-running immediately afterward prints nothing (no unread mail left, or previously-errored emails retry).

Then verify the tree was written:

```bash
uv run python -c "from brain import store; c = store.connect(); print([e['title'] for e in store.all_of_type(c, 'mail_category')])"
```

Expected: a list of category titles matching what was just ingested.

- [ ] **Step 7: Commit**

```bash
git add brain/mail_ingest.py brain/mail_config.json tests/test_mail_ingest.py
git commit -m "feat(brain): fetch/mark-read/run + CLI entry point for the mail pipeline"
```

---

## Self-Review Notes

- **Spec coverage:** node/edge model (Task 4), attachment handling incl. size caps (Task 2), classify+merge LLM calls (Task 3), OpenRouter provider + key rotation + small model default (Task 1), plain-Python CLI runnable via cron or on-demand (Task 5), config file for student id/resume/seeded categories (Task 5). Retrieval/asking questions and the Gmail-OAuth path are explicitly out of scope per the spec and are not tasked here.
- **Placeholder scan:** none — every step has complete, runnable code.
- **Type consistency:** `process_attachment(path, config) -> dict` (Task 2) matches its use in `gather_attachment_findings` (Task 4). `classify_email`/`merge_or_create_thread` signatures (Task 3) match their calls in `ingest_email` (Task 4) and their mocked signatures in tests. `ingest_email(conn, email, config) -> dict` (Task 4) matches its use in `run` (Task 5).
