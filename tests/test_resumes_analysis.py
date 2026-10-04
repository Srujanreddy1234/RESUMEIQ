import os

from resumeiq.models import ResumeVersion
from resumeiq.services import storage

from .conftest import make_docx


def test_upload_lists_and_extracts_skills(auth, uploaded):
    resume, version = uploaded
    assert resume["is_primary"] is True
    assert version["file_type"] == "txt" and version["original_filename"] == "priya.txt"
    assert "Java" in version["skills"]
    listing = auth.get("/api/resumes").get_json()
    assert listing["total"] == 1 and listing["items"][0]["latest_version"]["id"] == version["id"]


def test_upload_rejects_invalid_files(auth):
    r = auth.upload("/api/resumes", b"MZ fake binary", "resume.pdf")
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "content_mismatch"
    r = auth.upload("/api/resumes", b"hello", "resume.exe")
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "unsupported_file_type"
    r = auth.upload("/api/resumes", b"tiny", "resume.txt")
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "unreadable_resume"
    r = auth.post("/api/resumes", data={}, content_type="multipart/form-data")
    assert r.status_code == 400


def test_request_body_limit_returns_413(app, auth):
    app.config["MAX_CONTENT_LENGTH"] = 1000
    r = auth.upload("/api/resumes", b"x" * 5000, "big.txt")
    assert r.status_code == 413 and r.get_json()["error"]["code"] == "file_too_large"


def test_rename_primary_versions_compare_download_delete(app, auth, uploaded, resume_text):
    resume, v1 = uploaded
    rid = resume["id"]
    assert auth.patch(f"/api/resumes/{rid}", json={"name": "Backend CV"}).get_json()["name"] == "Backend CV"

    # Identical content can't be uploaded twice as a version
    dup = auth.upload(f"/api/resumes/{rid}/versions", resume_text.encode(), "priya.txt")
    assert dup.status_code == 409

    v2_text = resume_text.replace("Tools: Git, Docker, Postman, Linux", "Tools: Git, Docker, Kubernetes, Redis, Postman, Linux")
    v2 = auth.upload(f"/api/resumes/{rid}/versions", make_docx(v2_text.splitlines()), "priya-v2.docx").get_json()["version"]
    assert v2["version_number"] == 2

    cmp = auth.get(f"/api/resumes/compare?from={v1['id']}&to={v2['id']}").get_json()
    assert {"Kubernetes", "Redis"} <= set(cmp["added_skills"])

    dl = auth.get(f"/api/resumes/versions/{v1['id']}/download")
    assert dl.status_code == 200 and dl.data == resume_text.encode()
    assert "attachment" in dl.headers["Content-Disposition"]

    second = auth.upload("/api/resumes", resume_text.encode().replace(b"Priya", b"P."), "other.txt").get_json()["resume"]
    assert second["is_primary"] is False
    assert auth.post(f"/api/resumes/{second['id']}/primary").get_json()["is_primary"] is True

    stored = [v.stored_filename for v in ResumeVersion.query.filter_by(resume_id=rid)]
    assert auth.delete(f"/api/resumes/{rid}").status_code == 204
    for name in stored:
        assert not os.path.exists(storage.path_for(name))  # files removed from disk


def test_async_analysis_reports_real_stages(auth, uploaded):
    _, version = uploaded
    r = auth.post("/api/analysis", json={"resume_version_id": version["id"], "target_role": "Backend Developer"})
    assert r.status_code == 202
    task = r.get_json()["task"]
    assert task["status"] == "succeeded"
    statuses = {s["key"]: s["status"] for s in task["stages"]}
    assert statuses["read"] == "done" and statuses["score"] == "done"
    assert statuses["insights"] == "skipped"  # AI not configured in tests - shown honestly
    a = auth.get(f"/api/analysis/{task['result']['analysis_id']}").get_json()
    assert 0 < a["overall_score"] <= 100
    assert len(a["score_breakdown"]) == 10 and all(c["explanation"] for c in a["score_breakdown"])
    assert a["result"]["role_profile"] == "Backend Developer"
    assert "AI extraction unavailable" in a["result"]["ai_note"]
    assert auth.get(f"/api/tasks/{task['id']}").get_json()["status"] == "succeeded"


def test_analysis_validation(auth, uploaded):
    _, version = uploaded
    assert auth.post("/api/analysis", json={"resume_version_id": version["id"], "target_role": "x"}).status_code == 422
    assert auth.post("/api/analysis", json={"resume_version_id": 99999, "target_role": "Backend"}).status_code == 404


def test_history_pagination_and_deletion(auth, uploaded):
    _, version = uploaded
    for role in ("Backend Developer", "Java Developer", "Software Engineer"):
        auth.post("/api/analysis", json={"resume_version_id": version["id"], "target_role": role})
    page = auth.get("/api/analysis?per_page=2").get_json()
    assert page["total"] == 3 and len(page["items"]) == 2 and page["pages"] == 2
    filtered = auth.get("/api/analysis?role=java").get_json()
    assert filtered["total"] == 1
    assert auth.delete(f"/api/analysis/{page['items'][0]['id']}").status_code == 204
    assert auth.delete("/api/analysis").get_json()["deleted"] == 2
    assert auth.get("/api/analysis").get_json()["total"] == 0


JD = """Backend Engineer at Contoso
Requirements:
- 2+ years of experience building REST APIs with Java and Spring Boot
- Strong SQL and PostgreSQL skills, Docker
- Bachelor's degree in Computer Science
Nice to have:
- Redis and Kafka
- AWS Certified Cloud Practitioner
Strong communication skills."""


def test_ats_check_classifies_skills(auth, uploaded):
    _, version = uploaded
    r = auth.post("/api/analysis/ats", json={"resume_version_id": version["id"], "job_title": "Backend Engineer", "job_description": JD})
    assert r.status_code == 200
    d = r.get_json()
    by = {s["skill"]: s["status"] for s in d["skills"]}
    assert by["Java"] == "matched" and by["PostgreSQL"] == "matched"
    assert by["Spring Boot"] == "partial"          # transferable via Java
    assert by["Kafka"] == "missing"
    assert "React" in d["not_relevant"]
    assert "guarantee" in d["disclaimer"]
    assert 0 <= d["ats_score"] <= 100
    assert d["education"]["required"] == "bachelors"


def test_ats_rejects_too_short_job_description(auth, uploaded):
    _, version = uploaded
    r = auth.post("/api/analysis/ats", json={"resume_version_id": version["id"], "job_title": "Dev", "job_description": "Java dev"})
    assert r.status_code == 422


def test_job_description_analyzer(auth, uploaded):
    r = auth.post("/api/job-descriptions", json={"title": "Backend Engineer", "company": "Contoso", "text": JD})
    assert r.status_code == 201
    d = r.get_json()
    p = d["job_description"]["parsed"]
    assert "Spring Boot" in p["required_skills"] and "Redis" in p["preferred_skills"]
    assert p["experience_years"] == 2 and "Communication" in p["soft_skills"]
    assert d["comparison"]["ats_score"] >= 0
    assert auth.get("/api/job-descriptions").get_json()["total"] == 1
    bad = auth.post("/api/job-descriptions", json={"title": "Dev", "text": "too short"})
    assert bad.status_code == 422


def test_improvement_never_invents_numbers(auth, uploaded, fake_ai):
    _, version = uploaded
    fake_ai.queue("resume_improvement", {"items": [
        {"section": "projects", "original": "Made a website using Python", "explanation": "Stronger verb",
         "improved": "Built a Python web app that cut processing time by 40% for 2,000 users"},
        {"section": "projects", "original": "Something not in the resume", "improved": "x", "explanation": "x"},
    ], "improved_summary": None, "skills_section_advice": []})
    r = auth.post("/api/analysis/improve", json={"resume_version_id": version["id"], "scope": "projects"}).get_json()
    assert r["ai_used"]
    assert len(r["items"]) == 1  # hallucinated original dropped
    item = r["items"][0]
    assert "40%" not in item["improved"] and "2,000" not in item["improved"]
    assert item["needs_metric"] and "removed" in item["explanation"]


def test_improvement_fallback_uses_placeholders(auth, uploaded):
    _, version = uploaded
    r = auth.post("/api/analysis/improve", json={"resume_version_id": version["id"], "scope": "bullet",
                                                 "bullet": "Made a website using Python"}).get_json()
    assert not r["ai_used"]
    assert r["items"][0]["improved"].startswith("Built") and "[add measurable result]" in r["items"][0]["improved"]
