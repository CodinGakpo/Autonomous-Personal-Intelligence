"""Tests for the mail pipeline's local-first attachment handling (Excel/PDF)."""

from pathlib import Path

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
    assert result == {
        "headers": ["Name", "Student ID", "Status"],
        "row": ["Ravi", "S456", "Not Selected"],
    }


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
    profile = {"skills": ["Python"], "summary": "backend eng"}
    note = ma.match_resume_to_jd("Need Python dev", profile)
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
    monkeypatch.setattr(
        ma, "extract_pdf_text",
        lambda path, max_chars=ma.PDF_CHAR_CAP: "Hey, see you soon.",
    )
    path = tmp_path / "note.pdf"
    path.write_bytes(b"%PDF-1.4")
    result = ma.process_attachment(path, {})
    assert result["kind"] == "pdf"


def test_process_attachment_pdf_jd_with_resume(tmp_path, monkeypatch):
    jd_text = "Responsibilities: code. Requirements: Python. Qualifications: BS."
    monkeypatch.setattr(
        ma, "extract_pdf_text",
        lambda path, max_chars=ma.PDF_CHAR_CAP: jd_text,
    )
    monkeypatch.setattr(ma, "match_resume_to_jd", lambda jd, profile: "matches well")
    path = tmp_path / "jd.pdf"
    path.write_bytes(b"%PDF-1.4")
    result = ma.process_attachment(path, {"resume_profile": {"skills": ["Python"]}})
    assert result == {"file": "jd.pdf", "kind": "pdf_jd", "finding": "matches well"}
