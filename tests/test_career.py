from datetime import datetime, timedelta, timezone

from resumeiq.models import Notification


def test_skill_gap_statuses_and_evidence(auth, uploaded):
    g = auth.get("/api/skills/gap?role=Backend Developer").get_json()
    by = {i["skill"]: i for i in g["items"]}
    assert g["role_profile"] == "Backend Developer" and 0 <= g["readiness"] <= 100
    assert by["Redis"]["status"] == "missing" and by["Redis"]["current_level"] == 0
    assert all(i["evidence"] for i in g["items"])
    assert by["Redis"]["job_frequency"] is None  # no claim of market frequency without enough postings
    assert "curated baseline" in g["data_note"]
    ranks = [i["priority_rank"] for i in g["items"] if i["status"] != "strong"]
    assert sorted(ranks) == list(range(1, len(ranks) + 1))


def test_skill_gap_requires_role(auth):
    assert auth.get("/api/skills/gap").status_code == 422


def test_skill_graph_and_detail(auth, uploaded):
    graph = auth.get("/api/skills/graph?role=Backend Developer").get_json()
    assert graph["current"] and graph["target"] and graph["learning_path"]
    d = auth.get("/api/skills/detail?name=docker&role=Backend Developer").get_json()
    assert d["skill"]["name"] == "Docker" and d["resources"] and d["topics"]
    assert all(r["url"].startswith("https://") for r in d["resources"])


def test_roadmap_orders_prerequisites_first(auth, uploaded):
    auth.put("/api/profile", json={"target_career": "DevOps Engineer"})
    rm = auth.post("/api/roadmap", json={"target_role": "DevOps Engineer", "weekly_hours": 10}).get_json()
    order = [i["skill"]["name"] for i in rm["items"]]
    assert order and rm["estimated_weeks"] > 0
    if "Kubernetes" in order and "Docker" in order:
        assert order.index("Docker") < order.index("Kubernetes")
    item = rm["items"][0]
    assert item["what_to_learn"] and item["why"] and "beginner" in item["resources"]
    assert auth.get("/api/roadmap").get_json()["roadmap"]["id"] == rm["id"]


def test_learning_progress_and_milestones(app, auth, uploaded):
    rm = auth.post("/api/roadmap", json={"target_role": "Backend Developer"}).get_json()
    first = rm["items"][0]
    res = (first["resources"]["beginner"] + first["resources"]["intermediate"])
    curated = [r for r in res if not r["is_search_link"]]
    if curated:
        p = auth.put(f"/api/learning/progress/{curated[0]['id']}", json={"status": "completed", "hours_spent": 3}).get_json()
        assert p["status"] == "completed" and p["hours_spent"] == 3 and p["completed_at"]
    for it in rm["items"]:
        auth.patch(f"/api/roadmap/items/{it['id']}", json={"status": "completed"})
    view = auth.get("/api/roadmap").get_json()["roadmap"]
    assert view["progress"] == 100
    stats = auth.get("/api/learning/stats").get_json()
    assert stats["skills_completed"] == len(rm["items"])
    titles = [n.title for n in Notification.query.filter_by(type="learning")]
    assert any("100%" in t for t in titles)
    assert len(titles) == len(set(titles))  # milestones are de-duplicated


def test_project_recommendations_target_gaps(auth, uploaded):
    d = auth.get("/api/roadmap/projects?role=Backend Developer").get_json()
    assert d["projects"]
    for p in d["projects"]:
        assert set(p["skills_learned"]) <= set(d["missing_skills"]) | set(p["skills_learned"])
        assert p["skills_learned"] and p["features"] and p["duration_weeks"]
    done = auth.post("/api/learning/projects", json={"title": d["projects"][0]["title"], "technologies": ["docker"]})
    assert done.status_code == 201 and done.get_json()["technologies"] == ["Docker"]


def test_interview_prep_fallback_and_evaluation(auth, uploaded):
    r = auth.post("/api/interview/sessions", json={"mode": "prep", "target_role": "Backend Developer",
                                                   "categories": ["technical", "behavioral", "project"], "count": 5}).get_json()
    s = r["session"]
    assert len(s["questions"]) == 5 and not r["ai_used"]
    q = s["questions"][0]
    assert q["why_asked"] and q["strong_answer_points"] and q["common_mistakes"]
    ans = auth.post(f"/api/interview/sessions/{s['id']}/answers", json={
        "question_id": q["id"],
        "answer": "At my internship I built REST APIs in Java. The challenge was slow queries, so I added indexes "
                  "and caching, and as a result response times improved. I learned to measure before optimising."}).get_json()
    ev = ans["evaluation"]
    assert set(ev["scores"]) == {"communication", "technical_accuracy", "relevance", "structure"}
    assert "not judgments of personality" in ev["indicators"]["note"]


def test_mock_interview_flow_with_follow_up(auth, uploaded, fake_ai):
    fake_ai.queue("interview_questions", {"questions": [
        {"category": "technical", "difficulty": "medium", "question": "How do you design a REST API for orders?",
         "why_asked": "Core backend skill", "strong_answer_points": ["Resources and HTTP methods", "Status codes"],
         "common_mistakes": ["Verbs in URLs"]},
        {"category": "behavioral", "question": "Tell me about a conflict.", "why_asked": "Teamwork",
         "strong_answer_points": ["STAR"], "common_mistakes": ["Blame"]}]})
    fake_ai.queue("interview_evaluation", {"scores": {"communication": 7, "technical_accuracy": 6, "relevance": 8, "structure": 6},
                                           "feedback": "Good start.", "missing_concepts": ["Pagination"], "improvements": ["Mention idempotency"],
                                           "follow_up_question": "How would you version this API?"})
    s = auth.post("/api/interview/sessions", json={"mode": "mock", "target_role": "Backend Developer", "count": 2}).get_json()["session"]
    first = s["questions"][0]
    r = auth.post(f"/api/interview/sessions/{s['id']}/answers", json={"question_id": first["id"], "answer": "I would use /orders with GET and POST."}).get_json()
    assert r["follow_up"]["question"] == "How would you version this API?"
    assert r["next_question"]["is_follow_up"] is True
    fin = auth.post(f"/api/interview/sessions/{s['id']}/finish").get_json()["session"]
    assert fin["status"] == "completed" and fin["overall_score"] == 68
    assert "Pagination" in fin["summary"]["missing_concepts"]
    late = auth.post(f"/api/interview/sessions/{s['id']}/answers", json={"question_id": first["id"], "answer": "more"})
    assert late.status_code == 409


def test_application_tracker_and_analytics(auth):
    a = auth.post("/api/applications", json={"company": "Acme", "position": "Backend Developer", "stage": "applied"}).get_json()
    b = auth.post("/api/applications", json={"company": "Globex", "position": "Java Developer"}).get_json()
    assert a["date_applied"] and b["stage"] == "wishlist"
    auth.post(f"/api/applications/{b['id']}/move", json={"stage": "applied"})
    auth.post(f"/api/applications/{a['id']}/move", json={"stage": "interview", "position": 0})
    auth.post(f"/api/applications/{a['id']}/move", json={"stage": "rejected"})
    board = auth.get("/api/applications").get_json()
    assert [c["stage"] for c in board["columns"]] == ["wishlist", "applied", "assessment", "interview", "offer", "rejected"]
    hist = auth.get(f"/api/applications/{a['id']}").get_json()["history"]
    assert [h["to"] for h in hist] == ["applied", "interview", "rejected"]
    stats = auth.get("/api/analytics/applications").get_json()
    assert stats["applications_sent"] == 2 and stats["interviews"] == 1 and stats["interview_rate"] == 50
    assert stats["small_sample"] and "early signals" in stats["sample_note"]
    assert auth.patch(f"/api/applications/{a['id']}", json={"notes": "Recruiter: Sam"}).get_json()["notes"] == "Recruiter: Sam"
    assert auth.post("/api/applications", json={"company": "X", "position": "Y", "job_url": "javascript:alert(1)"}).status_code == 422
    assert auth.delete(f"/api/applications/{a['id']}").status_code == 204


def test_cover_letter_fallback_uses_only_resume_facts(auth, uploaded):
    r = auth.post("/api/cover-letter", json={"company": "Contoso", "position": "Backend Engineer", "tone": "concise"})
    assert r.status_code == 201
    letter = r.get_json()
    assert "Acme Corp" in letter["content"] and "Contoso" in letter["content"] and "[" in letter["content"]
    assert not letter["ai_used"]
    upd = auth.put(f"/api/cover-letter/{letter['id']}", json={"content": letter["content"] + "\nP.S. Edited."}).get_json()
    assert upd["content"].endswith("Edited.")
    assert auth.get("/api/cover-letter").get_json()["total"] == 1


def test_cover_letter_requires_resume(auth):
    r = auth.post("/api/cover-letter", json={"company": "Contoso", "position": "Engineer"})
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "resume_required"


def test_notifications_reminders_and_preferences(auth):
    soon = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    auth.post("/api/applications", json={"company": "Acme", "position": "Dev", "stage": "interview", "interview_date": soon})
    first = auth.get("/api/notifications").get_json()
    assert any(n["type"] == "interview" for n in first["items"])
    again = auth.get("/api/notifications").get_json()
    assert again["total"] == first["total"]  # reminders are idempotent
    nid = first["items"][0]["id"]
    assert auth.post(f"/api/notifications/{nid}/read").get_json()["is_read"]
    assert auth.post("/api/notifications/read-all").status_code == 200
    assert auth.get("/api/notifications/unread-count").get_json()["unread"] == 0
    assert auth.delete(f"/api/notifications/{nid}").status_code == 204
    auth.put("/api/profile", json={"notify_analysis": False})


def test_analysis_notification_respects_preferences(auth, uploaded):
    _, version = uploaded
    auth.put("/api/profile", json={"notify_analysis": False})
    auth.post("/api/analysis", json={"resume_version_id": version["id"], "target_role": "Backend Developer"})
    assert Notification.query.filter_by(type="analysis").count() == 0


def test_dashboard_and_insights(auth, uploaded):
    auth.post("/api/analysis", json={"resume_version_id": uploaded[1]["id"], "target_role": "Backend Developer"})
    d = auth.get("/api/analytics/dashboard").get_json()
    assert d["stats"]["resume_score"] and d["readiness"]["score"] is not None
    assert {c["label"] for c in d["readiness"]["components"]} >= {"Resume score", "Skill coverage"}
    assert d["top_gaps"] and d["recent_activity"]
    ins = auth.get("/api/analytics/insights").get_json()["insights"]
    assert ins and all(i["evidence"] for i in ins)
    assert any("measurable outcome" in i["text"] for i in ins)


def test_profile_sections_crud_and_skills(auth):
    e = auth.post("/api/profile/education", json={"institution": "MIT", "degree": "BSc", "graduation_year": 2025})
    assert e.status_code == 201
    eid = e.get_json()["id"]
    assert auth.put(f"/api/profile/education/{eid}", json={"institution": "MIT", "degree": "MSc"}).get_json()["degree"] == "MSc"
    assert auth.delete(f"/api/profile/education/{eid}").status_code == 204
    s = auth.post("/api/profile/skills", json={"skill": "k8s", "level": 4}).get_json()
    assert s["skill"]["name"] == "Kubernetes" and s["level"] == 4 and s["source"] == "self"
    g = auth.post("/api/profile/goals", json={"target_role": "Data Engineer", "is_primary": True}).get_json()
    assert g["is_primary"]
    assert auth.put("/api/profile", json={"salary_min": 100, "salary_max": 50}).status_code == 422
    assert auth.put("/api/profile", json={"github_url": "javascript:alert(1)"}).status_code == 422
    prof = auth.get("/api/profile").get_json()
    assert prof["profile"]["completeness"] >= 0 and prof["skills"]


def test_global_search(auth, uploaded):
    auth.post("/api/applications", json={"company": "Acme Robotics", "position": "Backend Developer"})
    r = auth.get("/api/search?q=backend").get_json()
    assert r["applications"] and any("Backend" in s["title"] for s in r["applications"])
    assert auth.get("/api/search?q=dock").get_json()["skills"][0]["title"] == "Docker"
    assert auth.get("/api/search?q=a").get_json()["jobs"] == []
