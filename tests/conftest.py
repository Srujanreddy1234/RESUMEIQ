import io
import os

import pytest

from resumeiq import create_app
from resumeiq.extensions import db as _db

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
PASSWORD = "Secret123!"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:"))
    from resumeiq.config import TestingConfig
    monkeypatch.setattr(TestingConfig, "STORAGE_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_DATABASE_URI", os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:"))
    application = create_app("testing")
    with application.app_context():
        _db.drop_all()
        _db.create_all()
        from resumeiq.services.roadmap import seed_resources
        from resumeiq.services.skill_extraction import seed_skills
        seed_skills()
        seed_resources()
        _db.session.commit()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


class AuthClient:
    """Test client wrapper that sends the CSRF header automatically (like the frontend does)."""

    def __init__(self, client, email):
        self.client = client
        self.email = email

    def _headers(self, kwargs):
        cookie = self.client.get_cookie("csrf_access_token")
        headers = kwargs.pop("headers", {}) or {}
        if cookie:
            headers.setdefault("X-CSRF-TOKEN", cookie.value)
        return headers

    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def post(self, url, **kw):
        return self.client.post(url, headers=self._headers(kw), **kw)

    def put(self, url, **kw):
        return self.client.put(url, headers=self._headers(kw), **kw)

    def patch(self, url, **kw):
        return self.client.patch(url, headers=self._headers(kw), **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self._headers(kw), **kw)

    def upload(self, url, data, filename, extra=None):
        payload = {"resume": (io.BytesIO(data), filename), **(extra or {})}
        return self.post(url, data=payload, content_type="multipart/form-data")


def register_and_login(app, email="priya@example.com", name="Priya Sharma"):
    client = app.test_client()
    r = client.post("/api/auth/register", json={"full_name": name, "email": email, "password": PASSWORD,
                                                "confirm_password": PASSWORD})
    assert r.status_code == 201, r.get_json()
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.get_json()
    return AuthClient(client, email)


@pytest.fixture()
def auth(app):
    return register_and_login(app)


@pytest.fixture()
def other(app):
    return register_and_login(app, "other@example.com", "Other User")


@pytest.fixture()
def resume_text():
    with open(os.path.join(FIXTURES, "sample_resume.txt"), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture()
def uploaded(auth, resume_text):
    """Upload the sample resume for `auth`; returns (resume_json, version_json)."""
    auth.put("/api/profile", json={"target_career": "Backend Developer"})
    r = auth.upload("/api/resumes", resume_text.encode(), "priya.txt")
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    return body["resume"], body["version"]


class FakeAI:
    """Stand-in for GeminiClient. Queue responses (model instances or exceptions) per service."""

    def __init__(self):
        self.responses = {}
        self.calls = []
        self.configured = True

    def queue(self, service, response):
        self.responses.setdefault(service, []).append(response)

    def available_for(self, user_id):
        return True

    def generate(self, *, service, prompt, schema, user_id=None, temperature=0.3, system=None):
        from resumeiq.services.ai import AIUnavailable
        self.calls.append({"service": service, "prompt": prompt})
        queue = self.responses.get(service) or []
        if not queue:
            raise AIUnavailable("upstream_error")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, schema) else schema.model_validate(item)


@pytest.fixture()
def fake_ai(app):
    fake = FakeAI()
    original = app.extensions["ai_client"]
    app.extensions["ai_client"] = fake
    yield fake
    app.extensions["ai_client"] = original


def make_docx(paragraphs):
    import docx
    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def make_pdf(lines):
    """Build a minimal, valid single-page PDF containing text (no external libraries)."""
    content = "BT /F1 11 Tf 50 750 Td 14 TL " + " ".join(
        "(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out
