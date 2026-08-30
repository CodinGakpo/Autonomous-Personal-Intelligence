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
    summary = resume_profile.get('summary') or resume_profile.get('headline') or ''
    prompt = (
        "You are screening ONE candidate against ONE job description. Reply with 2-3 short "
        "sentences: how well they match, and the clearest gap if any. No preamble, no markdown.\n\n"
        f"CANDIDATE SKILLS: {skills}\n"
        f"CANDIDATE SUMMARY: {summary}\n\n"
        f"JOB DESCRIPTION:\n{jd_text}"
    )
    return call_openrouter(prompt).strip()


def process_attachment(path: Path, config: dict) -> dict:
    """Dispatch one saved attachment file by suffix. Always returns a small, prompt-safe finding."""
    suffix = Path(path).suffix.lower()

    if suffix in EXCEL_SUFFIXES:
        match = extract_excel_match(path, config.get("student_id", ""))
        if match is None:
            return {
                "file": Path(path).name,
                "kind": "excel",
                "finding": "no matching row for student id",
            }
        return {
            "file": Path(path).name,
            "kind": "excel",
            "finding": dict(zip(match["headers"], match["row"], strict=True)),
        }

    if suffix == ".pdf":
        text = extract_pdf_text(path)
        if not looks_like_job_description(text):
            return {"file": Path(path).name, "kind": "pdf", "finding": text[:500]}
        resume_profile = config.get("resume_profile") or {}
        if resume_profile:
            note = match_resume_to_jd(text, resume_profile)
        else:
            note = "no résumé configured to match against"
        return {"file": Path(path).name, "kind": "pdf_jd", "finding": note}

    return {
        "file": Path(path).name,
        "kind": suffix.lstrip(".") or "unknown",
        "finding": "attachment not parsed",
    }
