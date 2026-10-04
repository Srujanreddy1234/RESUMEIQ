import os

import pytest

from resumeiq.models import AnalysisHistory, Resume, ResumeVersion, User
from resumeiq.services import storage
from resumeiq.web.routes import PAGES

from .conftest import PASSWORD, register_and_login


def test_users_cannot_access_each_others_data(auth, other, uploaded):
    resume, version = uploaded
    task = auth.post("/api/analysis", json={"resume_version_id": version["id"], "target_role": "Backend Developer"}).get_json()["task"]
    analysis_id = task["result"]["analysis_id"]
    app_id = auth.post("/api/applications", json={"company": "Acme", "position": "Dev"}).get_json()["id"]

    for url in (f"/api/resumes/{resume['id']}", f"/api/resumes/versions/{version['id']}",
                f"/api/resumes/versions/{version['id']}/download", f"/api/analysis/{analysis_id}",
                f"/api/applications/{app_id}", f"/api/tasks/{task['id']}"):
        assert other.get(url).status_code == 404, url  # 404, not 403: don't leak existence
    assert other.delete(f"/api/resumes/{resume['id']}").status_code == 404
    assert other.patch(f"/api/applications/{app_id}", json={"notes": "x"}).status_code == 404
    assert other.post("/api/analysis", json={"resume_version_id": version["id"], "target_role": "Backend"}).status_code == 404
    assert other.post("/api/analysis/ats", json={"resume_version_id": version["id"], "job_title": "Developer",
                                                 "job_description": "word " * 30}).status_code == 404
    assert other.get("/api/resumes").get_json()["total"] == 0
    assert other.get("/api/analysis").get_json()["total"] == 0


def test_admin_endpoints_require_admin(app, auth):
    assert auth.get("/api/admin/overview").status_code == 403
    assert auth.get("/api/admin/users").status_code == 403
    user = User.query.filter_by(email=auth.email).one()
    user.role = "admin"
    from resumeiq.extensions import db
    db.session.commit()
    assert auth.get("/api/admin/overview").status_code == 200


def test_admin_overview_contains_no_resume_content(app, auth, uploaded):
    from resumeiq.extensions import db
    User.query.filter_by(email=auth.email).one().role = "admin"
    db.session.commit()
    body = auth.get("/api/admin/overview").get_data(as_text=True)
    users = auth.get("/api/admin/users").get_data(as_text=True)
    for secret in ("Acme Corp", "Campus Marketplace", "priya.sharma@example.com", "Hackathon"):
        assert secret not in body and secret not in users
    data = auth.get("/api/admin/overview").get_json()
    assert data["users"]["total"] == 1 and data["resumes"] == 1


def test_deactivated_user_is_signed_out(app, auth, other):
    from resumeiq.extensions import db
    admin = User.query.filter_by(email=auth.email).one()
    admin.role = "admin"
    db.session.commit()
    target = User.query.filter_by(email=other.email).one()
    assert auth.patch(f"/api/admin/users/{target.id}", json={"is_active": False}).status_code == 200
    assert other.get("/api/auth/me").status_code == 401
    assert auth.patch(f"/api/admin/users/{admin.id}", json={"is_active": False}).status_code == 400  # no self-lockout


def test_delete_account_removes_everything(app, auth, uploaded):
    _, version = uploaded
    auth.post("/api/analysis", json={"resume_version_id": version["id"], "target_role": "Backend Developer"})
    stored = ResumeVersion.query.first().stored_filename
    assert os.path.exists(storage.path_for(stored))
    bad = auth.delete("/api/users/me", json={"password": "wrong", "confirm": "DELETE"})
    assert bad.status_code == 400
    assert auth.delete("/api/users/me", json={"password": PASSWORD, "confirm": "nope"}).status_code == 422
    r = auth.delete("/api/users/me", json={"password": PASSWORD, "confirm": "DELETE"})
    assert r.status_code == 200
    assert User.query.count() == 0 and Resume.query.count() == 0 and AnalysisHistory.query.count() == 0
    assert not os.path.exists(storage.path_for(stored))
    assert auth.get("/api/auth/me").status_code == 401


def test_export_contains_user_data(auth, uploaded):
    r = auth.get("/api/users/me/export")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    data = r.get_json()
    assert data["account"]["email"] == auth.email and data["resumes"] and "password_hash" not in r.get_data(as_text=True)


def test_health_and_docs(app):
    c = app.test_client()
    assert c.get("/health").get_json() == {"status": "healthy"}
    docs = c.get("/api/docs").get_json()
    paths = {r["path"] for r in docs["routes"]}
    assert {"/api/auth/login", "/api/resumes", "/api/jobs", "/api/interview/sessions", "/health"} <= paths


@pytest.mark.parametrize("key", [k for k in PAGES if k != "admin"])
def test_every_page_renders_when_signed_in(auth, key):
    r = auth.get(PAGES[key][0])
    assert r.status_code == 200, key
    html = r.get_data(as_text=True)
    assert f"js/pages/{key}.js" in html and "<script>" not in html  # no inline scripts (CSP)


def test_admin_page_forbidden_for_users_and_auth_pages_redirect(auth):
    assert auth.get("/admin").status_code == 403
    assert auth.get("/login").status_code == 302  # already signed in


@pytest.mark.parametrize("path", ["/", "/login", "/register", "/forgot-password", "/reset-password?token=x", "/privacy", "/terms"])
def test_public_pages_render(app, path):
    assert app.test_client().get(path).status_code == 200


@pytest.mark.parametrize("kind,query", [("career", ""), ("skill-gap", "?role=Backend Developer"), ("applications", "")])
def test_reports_render(auth, uploaded, kind, query):
    r = auth.get(f"/reports/{kind}{query}")
    assert r.status_code == 200 and "Save as PDF" in r.get_data(as_text=True)


def test_analysis_report_is_owner_only(app, auth, other, uploaded):
    _, version = uploaded
    aid = auth.post("/api/analysis", json={"resume_version_id": version["id"], "target_role": "Backend Developer"}).get_json()["task"]["result"]["analysis_id"]
    assert auth.get(f"/reports/analysis?id={aid}").status_code == 200
    assert other.get(f"/reports/analysis?id={aid}").status_code == 404


def test_page_silently_refreshes_expired_access_token(app):
    c = register_and_login(app, "refresh@example.com")
    c.client.delete_cookie("access_token")
    r = c.get("/dashboard")
    assert r.status_code == 200
    assert any(h.startswith("access_token=") for h in r.headers.getlist("Set-Cookie"))
