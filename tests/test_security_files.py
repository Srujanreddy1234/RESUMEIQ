import io
import logging
import os
import re

import pytest
from werkzeug.datastructures import FileStorage

from resumeiq.security import hash_password, normalize_email, password_problems, safe_url, verify_password
from resumeiq.services import storage
from resumeiq.services.observability import ScrubFilter, scrub
from resumeiq.services.text_extraction import ExtractionError, extract_text

from .conftest import make_docx, make_pdf


def fs(data, name):
    return FileStorage(stream=io.BytesIO(data), filename=name)


# ── Passwords & validation ──────────────────────────────────────────────
def test_password_hash_roundtrip():
    h = hash_password("Secret123!")
    assert h != "Secret123!" and h.startswith("$2b$")
    assert verify_password("Secret123!", h)
    assert not verify_password("secret123!", h)
    assert not verify_password("", h)
    assert hash_password("Secret123!") != h  # salted


def test_password_rules():
    assert password_problems("Secret123!") == []
    assert password_problems("short1")
    assert password_problems("onlyletters")
    assert password_problems("password123")


def test_email_normalisation():
    assert normalize_email("  Priya@Example.COM ") == "priya@example.com"
    with pytest.raises(ValueError):
        normalize_email("bad@")


def test_safe_url_blocks_script_urls():
    assert safe_url("https://github.com/x") == "https://github.com/x"
    for bad in ("javascript:alert(1)", "data:text/html,hi", "ftp://x"):
        with pytest.raises(ValueError):
            safe_url(bad)


def test_secrets_are_scrubbed_from_logs():
    text = "key=AIzaSyBmozXnW4swP1-kEG1dkCwYDD1jU9lWSuA token: eyJhbGciOi.eyJzdWIiOi.sig password=hunter2"
    out = scrub(text)
    assert "AIza" not in out and "hunter2" not in out and "eyJhbGciOi.eyJzdWIiOi.sig" not in out
    record = logging.LogRecord("x", logging.INFO, "", 0, "api_key=%s", ("AIzaSyBmozXnW4swP1-kEG1dkCwYDD1jU9lWSuA",), None)
    ScrubFilter().filter(record)
    assert "AIza" not in record.getMessage()


def test_no_hardcoded_api_keys_in_source():
    root = os.path.join(os.path.dirname(__file__), "..", "resumeiq")
    for folder, _, files in os.walk(root):
        for f in files:
            if f.endswith((".py", ".js", ".html")):
                with open(os.path.join(folder, f), encoding="utf-8", errors="ignore") as fh:
                    assert not re.search(r"AIza[0-9A-Za-z_\-]{35}", fh.read()), f"possible API key in {f}"


# ── File validation ─────────────────────────────────────────────────────
def test_accepts_valid_pdf_docx_txt(app):
    pdf = make_pdf(["Jane Doe", "Python developer"])
    assert storage.read_upload(fs(pdf, "cv.pdf"))[1] == "pdf"
    docx = make_docx(["Jane Doe", "Experience"])
    assert storage.read_upload(fs(docx, "cv.docx"))[1] == "docx"
    assert storage.read_upload(fs(b"Plain text resume", "cv.txt"))[1] == "txt"


@pytest.mark.parametrize("data,name,code", [
    (b"MZ\x90\x00 fake exe", "resume.pdf", "content_mismatch"),        # executable renamed to .pdf
    (b"%PDF-1.4 but called docx", "resume.docx", "content_mismatch"),
    (b"binary\x00\x00data", "resume.txt", "content_mismatch"),
    (b"#!/bin/sh\nrm -rf /", "resume.sh", "unsupported_file_type"),
    (b"<?php system($_GET[c]); ?>", "resume.php", "unsupported_file_type"),
    (b"%PDF-1.4", "resume.doc", "unsupported_file_type"),
])
def test_rejects_bad_files(app, data, name, code):
    with pytest.raises(storage.FileRejected) as exc:
        storage.read_upload(fs(data, name))
    assert exc.value.code == code


def test_rejects_macro_enabled_docx(app):
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w:document/>")
        zf.writestr("word/vbaProject.bin", "macro")
    with pytest.raises(storage.FileRejected):
        storage.read_upload(fs(buf.getvalue(), "cv.docx"))


def test_rejects_oversized_and_empty_files(app):
    app.config["MAX_RESUME_BYTES"] = 1024
    with pytest.raises(storage.FileRejected) as exc:
        storage.read_upload(fs(b"a" * 2048, "cv.txt"))
    assert exc.value.code == "file_too_large"
    with pytest.raises(storage.FileRejected):
        storage.read_upload(fs(b"", "cv.txt"))


def test_saved_files_use_random_names_outside_static(app):
    name, checksum = storage.save_bytes(b"hello", "txt")
    assert name.endswith(".txt") and len(name) == 36
    path = storage.path_for(name)
    assert "static" not in path
    assert oct(os.stat(path).st_mode)[-3:] == "600"  # not executable, owner-only
    storage.delete_file(name)
    assert not os.path.exists(path)


@pytest.mark.parametrize("bad", ["../../etc/passwd", "/etc/passwd", ".hidden", ""])
def test_path_traversal_is_blocked(app, bad):
    with pytest.raises(storage.FileRejected):
        storage.path_for(bad)


# ── Text extraction ─────────────────────────────────────────────────────
def test_extracts_text_from_all_formats():
    lines = ["Jane Doe", "jane@example.com", "Skills: Python, Docker, PostgreSQL and REST APIs for backend work"]
    assert "Docker" in extract_text(make_pdf(lines), "pdf")
    assert "PostgreSQL" in extract_text(make_docx(lines), "docx")
    assert "REST APIs" in extract_text("\n".join(lines).encode(), "txt")


def test_unreadable_resume_raises():
    with pytest.raises(ExtractionError):
        extract_text(b"too short", "txt")
    with pytest.raises(ExtractionError):
        extract_text(b"%PDF-1.4 garbage", "pdf")


# ── HTTP hardening ─────────────────────────────────────────────────────
def test_security_headers(app):
    r = app.test_client().get("/login")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Request-ID"]


def test_unexpected_errors_are_sanitised(app, auth, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret internal detail /etc/db password=hunter2")
    monkeypatch.setattr("resumeiq.services.analytics.global_search", boom)
    r = auth.get("/api/search?q=python")
    assert r.status_code == 500
    body = r.get_data(as_text=True)
    assert "hunter2" not in body and "Traceback" not in body and "secret internal" not in body
    assert r.get_json()["error"]["request_id"]


def test_sql_injection_attempt_is_harmless(auth):
    r = auth.get("/api/search?q=' OR 1=1; DROP TABLE users; --")
    assert r.status_code == 200
    assert auth.get("/api/auth/me").status_code == 200  # users table intact


def test_json_body_must_be_object(auth):
    r = auth.post("/api/applications", data="[1,2]", content_type="application/json")
    assert r.status_code == 422
