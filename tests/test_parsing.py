from resumeiq.services.improvement import guard_fabrication, rule_based_rewrite, weak_bullets
from resumeiq.services.job_sources import html_to_text, infer_level, parse_salary
from resumeiq.services.resume_parser import has_metric, parse_resume
from resumeiq.services.scoring import WEIGHTS, score_resume
from resumeiq.services.skill_extraction import (canonical_skill, classify_requirements, extract_education_level,
                                                extract_skills, extract_years_required, resolve_role, role_requirements)


def test_parse_resume_extracts_structure(resume_text):
    p = parse_resume(resume_text)
    c = p["contact"]
    assert c["name"] == "Priya Sharma"
    assert c["email"] == "priya.sharma@example.com"
    assert c["phone"] and c["github"].endswith("github.com/priyasharma") and "linkedin.com/in/priyasharma" in c["linkedin"]
    edu = p["education"][0]
    assert edu["institution"] == "State University" and edu["graduation_year"] == 2024 and edu["level"] == "bachelors"
    exp = p["experience"][0]
    assert exp["company"] == "Acme Corp" and exp["kind"] == "internship"
    assert "Worked on bug fixes in the legacy reporting module" in exp["bullets"]  # wrapped line re-joined
    assert [x["name"] for x in p["projects"]] == ["Campus Marketplace", "Expense Tracker"]
    assert p["certifications"] == ["AWS Certified Cloud Practitioner"]
    assert {"Java", "Python", "Docker", "PostgreSQL", "REST APIs", "Git"} <= set(p["skills"]["all"])


def test_skill_aliases_and_false_positives():
    found = extract_skills("Built APIs with Node.js, React.js and Postgres; used k8s, C++ and C#. Familiar with golang.")
    assert {"Node.js", "React", "PostgreSQL", "Kubernetes", "C++", "C#", "Go"} <= set(found)
    assert "Go" not in extract_skills("We plan our go-to-market strategy")
    assert "Spring Framework" not in extract_skills("Intern, Spring 2023 semester")
    assert "Spring Boot" in extract_skills("Services in Spring Boot") and "Spring Framework" not in extract_skills("Services in Spring Boot")
    assert "REST APIs" not in extract_skills("the rest of the team")
    assert "Java" not in extract_skills("JavaScript only")
    assert canonical_skill("reactjs") == "React" and canonical_skill("postgres") == "PostgreSQL"


def test_jd_required_vs_preferred():
    jd = """Backend Engineer
Requirements:
- 3+ years of experience with Java and Spring Boot
- Strong SQL and PostgreSQL
Nice to have:
- Redis, Kafka
Experience with AWS is a plus. Bachelor's degree in Computer Science."""
    required, preferred = classify_requirements(jd)
    assert {"Java", "Spring Boot", "SQL", "PostgreSQL"} <= set(required)
    assert {"Redis", "Kafka", "AWS"} <= set(preferred)
    assert not set(required) & set(preferred)
    assert extract_years_required(jd) == 3
    assert extract_education_level(jd) == "bachelors"


def test_role_resolution():
    assert resolve_role("Senior Backend Engineer") == "Backend Developer"
    assert resolve_role("Jr. Data Scientist II") == "Data Scientist"
    assert resolve_role("SDE") == "Software Engineer"
    name, reqs = role_requirements("backend developer", ["Python", "Django"])
    assert name == "Backend Developer"
    # any_of groups resolve to the option the user already has
    assert any(r["skill"] == "Python" and r.get("alternatives") for r in reqs)
    assert any(r["skill"] == "Django" for r in reqs)


def test_scoring_is_transparent_and_bounded(resume_text):
    p = parse_resume(resume_text)
    name, reqs = role_requirements("Backend Developer", p["skills"]["all"])
    s = score_resume(p, resume_text, "txt", name, reqs)
    keys = {c["key"] for c in s["components"]}
    assert keys == set(WEIGHTS)
    for c in s["components"]:
        assert 0 <= c["score"] <= 100
        assert c["explanation"] and isinstance(c["suggestions"], list)
    assert 0 <= s["overall"] <= 100
    projects = next(c for c in s["components"] if c["key"] == "projects")
    assert "measurable" in projects["explanation"]
    # deterministic
    assert score_resume(p, resume_text, "txt", name, reqs)["overall"] == s["overall"]


def test_better_resume_scores_higher(resume_text):
    improved = resume_text.replace("• Made a website using Python", "• Built a Flask site serving 300 students, cutting listing time by 40%")
    a = score_resume(parse_resume(resume_text), resume_text, "txt")["overall"]
    b = score_resume(parse_resume(improved), improved, "txt")["overall"]
    assert b > a


def test_metric_detection():
    assert has_metric("Reduced latency by 40%")
    assert has_metric("Served 10k users")
    assert not has_metric("Made a website using Python")


def test_fabrication_guard_removes_invented_numbers():
    text, fabricated = guard_fabrication("Made a website using Python.", "Built a Python site that cut processing time by 40% for 500 users.")
    assert fabricated and "40%" not in text and "500" not in text and "[X]" in text
    text, fabricated = guard_fabrication("Raised coverage from 52% to 78%", "Increased test coverage from 52% to 78% with JUnit")
    assert not fabricated and "52%" in text and "78%" in text


def test_rule_based_rewrite_adds_placeholder_not_numbers():
    improved, needs = rule_based_rewrite("Made a website using Python")
    assert improved.startswith("Built") and needs and "[add measurable result]" in improved
    assert not any(ch.isdigit() for ch in improved)


def test_weak_bullets_are_flagged(resume_text):
    weak = weak_bullets(parse_resume(resume_text))
    texts = [w["text"] for w in weak]
    assert "Responsible for documentation" in texts
    assert all(w["reasons"] for w in weak)


def test_job_normalisation_helpers():
    assert parse_salary("$80k - $100k") == (80000, 100000, "USD")
    assert parse_salary("$45/hour")[0] == 45 * 2080
    assert parse_salary("competitive") == (None, None, None)
    assert infer_level("Junior Backend Developer", "", None) == "entry"
    assert infer_level("Staff Engineer", "", None) == "senior"
    assert infer_level("Backend Developer", "", 4) == "mid"
    assert "<script>" not in html_to_text("<p>Hello<script>alert(1)</script></p><ul><li>Java</li></ul>").replace("alert(1)", "")
    assert "• Java" in html_to_text("<ul><li>Java</li></ul>")
