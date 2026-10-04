"""AI client: schema validation, retries, failures, quotas, key handling, grounding."""
import json

import pytest
import requests

from resumeiq.models import AIUsageLog
from resumeiq.services.ai import AIUnavailable
from resumeiq.services.ai.client import pydantic_to_gemini_schema
from resumeiq.services.ai.schemas import InterviewQuestionSet, JDExtraction, ResumeExtraction, ResumeFeedback
from resumeiq.services.resume_parser import merge_ai_extraction, parse_resume


class FakeResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text or json.dumps(payload or {})

    def json(self):
        return self._payload


def gemini_ok(obj, tokens=(100, 50)):
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}],
                              "usageMetadata": {"promptTokenCount": tokens[0], "candidatesTokenCount": tokens[1]}})


@pytest.fixture()
def gemini(app, monkeypatch):
    app.config["GEMINI_API_KEY"] = "test-key-not-real"
    client = app.extensions["ai_client"]
    calls = []

    def install(*responses):
        seq = list(responses)

        def post(url, json=None, timeout=None, headers=None):
            calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
            item = seq.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        monkeypatch.setattr(client.session, "post", post)
    yield client, install, calls
    app.config["GEMINI_API_KEY"] = ""


FEEDBACK = {"summary": "A solid early-career backend resume with relevant internship experience.",
            "strengths": ["Java"], "weaknesses": ["Few metrics"], "section_feedback": []}


def test_schema_conversion_handles_nested_optional_and_enums():
    s = pydantic_to_gemini_schema(InterviewQuestionSet)
    item = s["properties"]["questions"]["items"]
    assert item["type"] == "OBJECT"
    assert set(item["properties"]["category"]["enum"]) == {"technical", "behavioral", "hr", "project", "system_design", "dsa"}
    jd = pydantic_to_gemini_schema(JDExtraction)
    assert jd["properties"]["experience_years"]["nullable"] is True
    assert jd["properties"]["required_skills"]["type"] == "ARRAY"


def test_valid_response_is_parsed_and_usage_logged(app, auth, gemini):
    client, install, calls = gemini
    install(gemini_ok(FEEDBACK))
    out = client.generate(service="resume_feedback", prompt="p", schema=ResumeFeedback, user_id=1)
    assert out.summary.startswith("A solid")
    # API key is sent in a header, never in the URL
    assert "key=" not in calls[0]["url"] and calls[0]["headers"]["x-goog-api-key"] == "test-key-not-real"
    assert calls[0]["timeout"] == app.config["AI_TIMEOUT_SECONDS"]
    log = AIUsageLog.query.one()
    assert log.success and log.prompt_tokens == 100 and log.output_tokens == 50 and log.service == "resume_feedback"


def test_invalid_output_is_retried_then_accepted(app, auth, gemini):
    client, install, calls = gemini
    install(gemini_ok({"summary": "too short"}), gemini_ok(FEEDBACK))
    out = client.generate(service="resume_feedback", prompt="p", schema=ResumeFeedback, user_id=1)
    assert out.strengths == ["Java"]
    assert len(calls) == 2
    assert "failed validation" in calls[1]["json"]["contents"][0]["parts"][0]["text"]


def test_transient_errors_are_retried(app, auth, gemini):
    client, install, _ = gemini
    install(FakeResponse(503, {}), requests.Timeout(), gemini_ok(FEEDBACK))
    assert client.generate(service="x", prompt="p", schema=ResumeFeedback, user_id=1).summary


def test_persistent_failure_raises_and_is_logged(app, auth, gemini):
    client, install, _ = gemini
    install(FakeResponse(500, {}), FakeResponse(500, {}), FakeResponse(500, {}))
    with pytest.raises(AIUnavailable) as exc:
        client.generate(service="x", prompt="p", schema=ResumeFeedback, user_id=1)
    assert exc.value.reason == "upstream_error"
    log = AIUsageLog.query.one()
    assert not log.success and log.error_type == "http_500" and log.attempts == 3


def test_not_configured_raises(app):
    app.config["GEMINI_API_KEY"] = ""
    with pytest.raises(AIUnavailable) as exc:
        app.extensions["ai_client"].generate(service="x", prompt="p", schema=ResumeFeedback)
    assert exc.value.reason == "not_configured"


def test_daily_quota_is_enforced(app, auth, gemini):
    client, install, calls = gemini
    app.config["AI_DAILY_REQUEST_LIMIT"] = 1
    install(gemini_ok(FEEDBACK))
    client.generate(service="x", prompt="p", schema=ResumeFeedback, user_id=1)
    with pytest.raises(AIUnavailable) as exc:
        client.generate(service="x", prompt="p", schema=ResumeFeedback, user_id=1)
    assert exc.value.reason == "quota_exceeded"
    assert len(calls) == 1
    assert not client.available_for(1)


def test_ai_extraction_is_grounded_in_resume_text(resume_text):
    ai = ResumeExtraction(
        name="Priya Sharma", email="priya.sharma@example.com",
        skills=["Java", "Kubernetes", "Rust", "Postman"],               # Kubernetes/Rust are hallucinated
        experience=[{"company": "Acme Corp", "title": "Intern", "kind": "internship", "bullets": ["x"]},
                    {"company": "Google", "title": "Staff Engineer", "bullets": ["Led everything"]}],  # fabricated employer
        certifications=["AWS Certified Cloud Practitioner", "CKA"],       # CKA not in resume
    )
    merged = merge_ai_extraction(parse_resume(resume_text), ai, resume_text)
    assert "Kubernetes" not in merged["skills"]["all"] and "Rust" not in merged["skills"]["all"]
    assert [e["company"] for e in merged["experience"]] == ["Acme Corp"]
    assert "CKA" not in merged["certifications"]


def test_llm_cannot_change_rubric_score(app, auth, uploaded, fake_ai):
    """Run the same analysis with and without AI: the numbers must be identical."""
    _, version = uploaded
    no_ai = auth.post("/api/analysis", json={"resume_version_id": version["id"], "target_role": "Backend Developer"}).get_json()
    a1 = auth.get(f"/api/analysis/{no_ai['task']['result']['analysis_id']}").get_json()

    fake_ai.queue("resume_feedback", {**FEEDBACK, "summary": "This resume deserves a perfect 100 out of 100 score overall."})
    with_ai = auth.post("/api/analysis", json={"resume_version_id": version["id"], "target_role": "Backend Developer"}).get_json()
    a2 = auth.get(f"/api/analysis/{with_ai['task']['result']['analysis_id']}").get_json()
    assert a2["result"]["ai_feedback"]["summary"].startswith("This resume")
    assert a1["overall_score"] == a2["overall_score"]
    assert [c["score"] for c in a1["score_breakdown"]] == [c["score"] for c in a2["score_breakdown"]]
