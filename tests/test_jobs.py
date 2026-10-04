from datetime import datetime, timedelta, timezone

import pytest
import requests

from resumeiq.models import Job, JobSkill, JobSourceFetch
from resumeiq.services import job_sources


def posting(i, title="Backend Developer", skills="Java, Spring Boot, PostgreSQL, Docker", extra="", remote=True, salary=None):
    return {"external_id": f"ext-{i}", "title": title, "company": f"Company {i}", "location": "Remote" if remote else "Berlin",
            "work_type": "remote" if remote else "onsite", "employment_type": "full time", "salary_text": None,
            "salary_min": salary[0] if salary else None, "salary_max": salary[1] if salary else None,
            "salary_currency": "USD" if salary else None,
            "description": f"Requirements:\n- 2+ years experience with {skills}\n{extra}", "url": f"https://example.com/jobs/{i}",
            "posted_at": datetime.now(timezone.utc) - timedelta(days=i)}


@pytest.fixture()
def provider(app, monkeypatch):
    calls = {"n": 0}

    class Fake:
        name = "remotive"

        def enabled(self):
            return True

        def fetch(self, query, location):
            calls["n"] += 1
            if calls.get("fail"):
                raise requests.ConnectionError("down")
            return [posting(1), posting(2, "Senior Java Engineer", "Java, Kafka, Kubernetes"),
                    posting(3, "Frontend Developer", "React, TypeScript, CSS", remote=False),
                    posting(4, "Backend Engineer", "Python, Django, PostgreSQL", salary=(90000, 120000)),
                    posting(5, "Junior Backend Developer", "Java, SQL, REST APIs, Git", salary=(60000, 75000))]

    monkeypatch.setitem(job_sources.PROVIDERS, "remotive", Fake())
    app.config["JOB_PROVIDERS"] = ["remotive"]
    return calls


def test_ingest_extracts_skills_and_levels(app, provider):
    with app.test_request_context():
        status = job_sources.refresh("backend", None)
    assert status == {"remotive": "ok (5 new)"}
    job = Job.query.filter_by(external_id="ext-2").one()
    assert job.experience_level == "senior"
    assert {"Java", "Kafka", "Kubernetes"} <= set(job.skill_names())
    assert Job.query.filter_by(external_id="ext-5").one().experience_level == "entry"
    assert JobSkill.query.count() > 10


def test_search_scores_and_explains_matches(auth, uploaded, provider):
    d = auth.get("/api/jobs?q=backend").get_json()
    assert d["sources"]["remotive"].startswith("ok")
    assert d["total"] >= 3
    scores = [j["match"]["score"] for j in d["items"]]
    assert scores == sorted(scores, reverse=True)
    top = d["items"][0]
    assert top["match"]["explanation"]["why"] and "verdict" in top["match"]["explanation"]
    assert set(top["match"]["components"]) == {"skills", "experience", "title", "education", "location"}
    assert all(j["url"].startswith("https://") for j in d["items"])


def test_job_search_is_cached_per_query(auth, uploaded, provider):
    auth.get("/api/jobs?q=backend")
    second = auth.get("/api/jobs?q=backend").get_json()
    assert provider["n"] == 1 and second["sources"]["remotive"] == "cached"
    assert JobSourceFetch.query.count() == 1


def test_provider_outage_degrades_gracefully(auth, uploaded, provider):
    provider["fail"] = True
    d = auth.get("/api/jobs?q=backend")
    assert d.status_code == 200
    assert d.get_json()["sources"]["remotive"] == "unavailable"


def test_filters(auth, uploaded, provider):
    auth.get("/api/jobs?q=developer")
    assert all(j["work_type"] == "remote" for j in auth.get("/api/jobs?q=developer&work_type=remote").get_json()["items"])
    entry = auth.get("/api/jobs?experience_level=entry&sort=date").get_json()["items"]
    assert entry and all(j["experience_level"] == "entry" for j in entry)
    paid = auth.get("/api/jobs?salary_min=100000&sort=date").get_json()["items"]
    assert [j["external_id"] if "external_id" in j else j["company"] for j in paid] == ["Company 4"]
    kafka = auth.get("/api/jobs?skills=Kafka&sort=date").get_json()["items"]
    assert [j["company"] for j in kafka] == ["Company 2"]
    assert auth.get("/api/jobs?experience_level=wizard").status_code == 422


def test_save_apply_and_detail(auth, uploaded, provider):
    jobs = auth.get("/api/jobs?q=backend").get_json()["items"]
    jid = jobs[0]["id"]
    assert auth.post(f"/api/jobs/{jid}/save", json={}).status_code == 201
    saved = auth.get("/api/jobs?saved=1").get_json()
    assert saved["total"] == 1 and saved["items"][0]["saved"]
    app_ = auth.post(f"/api/jobs/{jid}/apply", json={"stage": "applied"}).get_json()
    assert app_["stage"] == "applied" and app_["date_applied"]
    detail = auth.get(f"/api/jobs/{jid}").get_json()
    assert detail["saved"] and detail["application_id"] == app_["id"] and "description" in detail
    assert auth.delete(f"/api/jobs/{jid}/save").status_code == 204
    assert auth.get("/api/jobs/999999").status_code == 404


def test_matches_endpoint(auth, uploaded, provider):
    auth.get("/api/jobs?q=backend")
    d = auth.get("/api/matches?limit=3").get_json()
    assert len(d["items"]) <= 3
    jid = d["items"][0]["id"]
    m = auth.get(f"/api/matches/{jid}").get_json()
    assert "matched_skills" in m and "explanation" in m


def test_salary_separates_data_and_interpretation(auth, uploaded, provider):
    auth.get("/api/jobs?q=backend")
    d = auth.get("/api/salary?role=Backend Developer").get_json()
    assert d["postings"]["sample_size"] == 2
    assert d["postings"]["levels"]["entry"]["sufficient"] is False  # small samples are not reported as ranges
    assert d["adzuna"]["available"] is False
    interp = auth.post("/api/salary/interpret", json={"role": "Backend Developer"}).get_json()
    assert interp["interpretation"]["available"] is False  # AI not configured; data still returned
    assert interp["data"]["postings"]["sample_size"] == 2
