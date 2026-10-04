"""Dashboard, career insights, application analytics, global search and admin metrics.

Every insight is computed from stored user data and carries its evidence.
"""
from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import case, func, or_

from ..extensions import db
from ..models import (STAGES, AIUsageLog, AnalysisHistory, Application, ApplicationEvent, CareerGoal, InterviewSession,
                      Job, LearningProgress, LearningResource, Profile, Resume, ResumeVersion, SavedJob, Skill, SkillGap,
                      SystemEvent, User, UserSkill, iso, utcnow)
from .observability import latency_snapshot
from .roadmap import active_roadmap, roadmap_view
from .skill_extraction import resolve_role

SMALL_SAMPLE = 10


def _month(dt):
    return dt.strftime("%Y-%m") if dt else None


def application_analytics(user_id):
    apps = Application.query.filter_by(user_id=user_id).all()
    events = ApplicationEvent.query.join(Application).filter(Application.user_id == user_id).all()
    reached = defaultdict(set)
    for e in events:
        reached[e.application_id].add(e.to_stage)
    for a in apps:
        reached[a.id].add(a.stage)
    sent = [a for a in apps if reached[a.id] - {"wishlist"}]
    responded = [a for a in sent if reached[a.id] & {"assessment", "interview", "offer", "rejected"}]
    interviews = [a for a in sent if reached[a.id] & {"interview", "offer"}]
    offers = [a for a in sent if "offer" in reached[a.id]]
    by_month = Counter(_month(a.date_applied or a.created_at) for a in sent)
    by_role = Counter(resolve_role(a.position) or a.position for a in sent)
    by_company = Counter(a.company for a in sent)
    n = len(sent)
    return {
        "total_tracked": len(apps), "applications_sent": n, "responses": len(responded), "interviews": len(interviews),
        "offers": len(offers),
        "response_rate": round(100 * len(responded) / n) if n else None,
        "interview_rate": round(100 * len(interviews) / n) if n else None,
        "offer_rate": round(100 * len(offers) / n) if n else None,
        "by_stage": {s: sum(1 for a in apps if a.stage == s) for s in STAGES},
        "by_month": [{"month": k, "count": v} for k, v in sorted(by_month.items()) if k],
        "by_role": [{"role": k, "count": v} for k, v in by_role.most_common(8)],
        "by_company": [{"company": k, "count": v} for k, v in by_company.most_common(8)],
        "small_sample": n < SMALL_SAMPLE,
        "sample_note": (f"Based on {n} application(s). With fewer than {SMALL_SAMPLE}, rates swing a lot with each "
                        "response - treat them as early signals, not conclusions.") if n < SMALL_SAMPLE else None,
    }


def interview_readiness(user_id):
    sessions = (InterviewSession.query.filter_by(user_id=user_id, status="completed")
                .filter(InterviewSession.overall_score.isnot(None))
                .order_by(InterviewSession.completed_at.desc()).limit(3).all())
    if not sessions:
        return None, 0
    return round(sum(s.overall_score for s in sessions) / len(sessions)), len(sessions)


def latest_primary_analysis(user_id):
    return (AnalysisHistory.query.join(ResumeVersion, AnalysisHistory.resume_version_id == ResumeVersion.id)
            .join(Resume).filter(AnalysisHistory.user_id == user_id, Resume.is_primary.is_(True))
            .order_by(AnalysisHistory.created_at.desc()).first()
            or AnalysisHistory.query.filter_by(user_id=user_id).order_by(AnalysisHistory.created_at.desc()).first())


def dashboard(user):
    from .job_matching import top_matches
    from .skill_gap import compute_skill_gap
    profile = Profile.query.filter_by(user_id=user.id).first()
    target = profile.target_career if profile else None
    analysis = latest_primary_analysis(user.id)
    resume_score = analysis.overall_score if analysis else None
    skills_count = UserSkill.query.filter_by(user_id=user.id).count()
    gap = compute_skill_gap(user.id, target, persist=False) if target else None
    gaps = [i for i in (gap["items"] if gap else []) if i["status"] != "strong"]
    roadmap = active_roadmap(user.id)
    learning_pct = roadmap_view(user.id, roadmap)["progress"] if roadmap else None
    interview_score, interview_n = interview_readiness(user.id)
    apps = application_analytics(user.id)
    recommended, matched_count = top_matches(user, 3) if target else ([], 0)
    completeness = profile.completeness() if profile else 0

    parts = [("Resume score", resume_score, 0.30), ("Skill coverage", gap["readiness"] if gap else None, 0.35),
             ("Interview practice", interview_score, 0.15), ("Learning progress", learning_pct, 0.10),
             ("Profile completeness", completeness, 0.10)]
    used = [(label, v, w) for label, v, w in parts if v is not None]
    readiness = round(sum(v * w for _, v, w in used) / sum(w for _, _, w in used)) if used else None

    return {
        "user": {"name": user.full_name, "first_name": user.full_name.split()[0]},
        "target_role": target,
        "readiness": {"score": readiness, "components": [{"label": label, "value": v, "weight": w} for label, v, w in parts],
                      "formula": "Weighted average of the available components; missing components are excluded and the "
                                 "remaining weights re-normalised."},
        "stats": {"resume_score": resume_score, "profile_completeness": completeness, "skills": skills_count,
                  "skill_gaps": len(gaps), "job_matches": matched_count, "applications_sent": apps["applications_sent"],
                  "interviews": apps["interviews"], "interview_readiness": interview_score,
                  "interview_sessions": interview_n},
        "top_gaps": [{"skill": g["skill"], "current_level": g["current_level"], "required_level": g["required_level"],
                      "importance": g["importance"]} for g in gaps[:3]],
        "recommended_jobs": recommended,
        "pipeline": apps["by_stage"],
        "learning": {"progress": learning_pct, "role": roadmap.target_role if roadmap else None},
        "charts": charts(user.id),
        "recent_activity": recent_activity(user.id),
        "has_resume": Resume.query.filter_by(user_id=user.id).count() > 0,
    }


def charts(user_id):
    analyses = (AnalysisHistory.query.filter_by(user_id=user_id).order_by(AnalysisHistory.created_at).limit(50).all())
    skills = UserSkill.query.filter_by(user_id=user_id).order_by(UserSkill.created_at).all()
    cumulative, running = [], 0
    by_month = Counter(_month(s.created_at) for s in skills)
    for month in sorted(by_month):
        running += by_month[month]
        cumulative.append({"month": month, "total": running})
    apps = Application.query.filter_by(user_id=user_id).all()
    app_months = Counter(_month(a.date_applied or a.created_at) for a in apps if a.stage != "wishlist")
    sessions = InterviewSession.query.filter_by(user_id=user_id).all()
    sess_months = Counter(_month(s.created_at) for s in sessions)
    learning = Counter(_month(p.completed_at) for p in LearningProgress.query.filter_by(user_id=user_id, status="completed").all())
    return {
        "resume_scores": [{"date": a.created_at.date().isoformat(), "score": a.overall_score, "kind": a.kind}
                          for a in analyses if a.overall_score is not None],
        "skills_over_time": cumulative,
        "applications_by_month": [{"month": k, "count": v} for k, v in sorted(app_months.items()) if k],
        "interviews_by_month": [{"month": k, "count": v} for k, v in sorted(sess_months.items()) if k],
        "learning_by_month": [{"month": k, "count": v} for k, v in sorted(learning.items()) if k],
    }


def recent_activity(user_id, limit=10):
    items = []
    for a in AnalysisHistory.query.filter_by(user_id=user_id).order_by(AnalysisHistory.created_at.desc()).limit(5):
        items.append({"type": "analysis", "title": f"Resume analysed for {a.target_role}", "detail": f"Score {a.overall_score}",
                      "at": iso(a.created_at), "link": f"/analyzer?analysis={a.id}"})
    for s in SavedJob.query.filter_by(user_id=user_id).order_by(SavedJob.created_at.desc()).limit(5):
        items.append({"type": "saved_job", "title": f"Saved {s.job.title}", "detail": s.job.company, "at": iso(s.created_at),
                      "link": "/jobs?saved=1"})
    for a in Application.query.filter_by(user_id=user_id).order_by(Application.updated_at.desc()).limit(5):
        items.append({"type": "application", "title": f"{a.position} at {a.company}", "detail": a.stage.capitalize(),
                      "at": iso(a.updated_at), "link": "/applications"})
    for p in (LearningProgress.query.filter_by(user_id=user_id, status="completed")
              .order_by(LearningProgress.completed_at.desc()).limit(5)):
        items.append({"type": "learning", "title": f"Completed: {p.resource.title}", "detail": p.resource.skill.name,
                      "at": iso(p.completed_at), "link": "/roadmap"})
    for s in InterviewSession.query.filter_by(user_id=user_id).order_by(InterviewSession.created_at.desc()).limit(5):
        items.append({"type": "interview", "title": f"{'Mock interview' if s.mode == 'mock' else 'Interview prep'}: {s.target_role}",
                      "detail": f"Score {s.overall_score}" if s.overall_score is not None else s.status,
                      "at": iso(s.created_at), "link": f"/interview?session={s.id}"})
    items.sort(key=lambda x: x["at"] or "", reverse=True)
    return items[:limit]


def career_insights(user):
    """Deterministic, evidence-backed insights."""
    from .skill_gap import compute_skill_gap
    from .skill_extraction import ROLE_PROFILES, SKILL_BY_NAME
    profile = Profile.query.filter_by(user_id=user.id).first()
    target = profile.target_career if profile else None
    skills = {us.skill.name: us.level for us in UserSkill.query.filter_by(user_id=user.id).all()}
    out = []

    by_cat = defaultdict(list)
    for s in skills:
        by_cat[SKILL_BY_NAME.get(s, {}).get("category", "other")].append(s)
    if by_cat:
        cat, names = max(by_cat.items(), key=lambda kv: len(kv[1]))
        if len(names) >= 3 and cat != "soft":
            out.append({"type": "strength", "text": f"Your broadest skill area is {cat} ({len(names)} skills: {', '.join(sorted(names)[:5])}).",
                        "evidence": [f"{len(names)} {cat} skills in your profile"], "link": "/profile"})

    if target:
        role = resolve_role(target)
        profile_def = ROLE_PROFILES.get(role or "", {})
        for group in profile_def.get("any_of", []):
            langs = {"Java", "Python", "Node.js", "Go", "C#", "JavaScript", "C++", "Kotlin", "Swift", "Dart"}
            if not (set(group) & set(skills)) and not (set(group) <= langs):
                have_langs = sorted(set(skills) & langs)
                if have_langs:
                    out.append({"type": "gap", "text": f"You have {', '.join(have_langs[:3])} but no {role} framework from: "
                                                       f"{', '.join(group[:5])}.",
                                "evidence": [f"{role} baseline expects one of {', '.join(group)}"], "link": "/skill-gap"})
        gap = compute_skill_gap(user.id, target, persist=False)
        missing = [i for i in gap["items"] if i["status"] == "missing"]
        if gap["items"]:
            freq_missing = [i for i in missing if i["job_frequency"]]
            if freq_missing:
                top = sorted(freq_missing, key=lambda i: -i["job_frequency"])[:3]
                out.append({"type": "gap", "text": "Skills frequently requested in stored " + (role or target) + " postings that you haven't listed: "
                                                   + ", ".join(f"{i['skill']} ({round(i['job_frequency'] * 100)}%)" for i in top) + ".",
                            "evidence": [gap["data_note"]], "link": "/skill-gap"})
            elif missing:
                out.append({"type": "gap", "text": f"{len(missing)} of {len(gap['items'])} skills in your {target} requirements are not on "
                                                   f"your profile yet (top priority: {missing[0]['skill']}).",
                            "evidence": missing[0]["evidence"], "link": "/skill-gap"})
    else:
        out.append({"type": "action", "text": "Set a target career in your profile to unlock role-specific gap analysis.",
                    "evidence": ["No target career set"], "link": "/profile"})

    analysis = latest_primary_analysis(user.id)
    if analysis:
        comps = {c["key"]: c for c in analysis.score_breakdown}
        proj = comps.get("projects")
        if proj and proj["evidence"].get("projects") and proj["evidence"].get("with_metrics", 0) < proj["evidence"]["projects"]:
            out.append({"type": "action", "text": f"Your resume has {proj['evidence']['projects']} project(s) but only "
                                                  f"{proj['evidence']['with_metrics']} describe a measurable outcome.",
                        "evidence": [proj["explanation"]], "link": "/improve"})
        weakest = min(analysis.score_breakdown, key=lambda c: c["score"])
        out.append({"type": "action", "text": f"Your weakest resume area is {weakest['label']} ({weakest['score']}/100).",
                    "evidence": [weakest["explanation"]], "link": f"/analyzer?analysis={analysis.id}"})
        history = (AnalysisHistory.query.filter_by(user_id=user.id).filter(AnalysisHistory.overall_score.isnot(None))
                   .order_by(AnalysisHistory.created_at).all())
        if len(history) >= 2 and history[-1].overall_score != history[0].overall_score:
            delta = history[-1].overall_score - history[0].overall_score
            out.append({"type": "trend", "text": f"Your resume score has {'risen' if delta > 0 else 'fallen'} by {abs(delta)} points "
                                                 f"across {len(history)} analyses.",
                        "evidence": [f"First {history[0].overall_score}, latest {history[-1].overall_score}"], "link": "/history"})
    else:
        out.append({"type": "action", "text": "Upload and analyse a resume to get resume-based insights.",
                    "evidence": ["No analyses yet"], "link": "/resumes"})

    apps = application_analytics(user.id)
    if apps["applications_sent"]:
        text = f"You've sent {apps['applications_sent']} application(s) with a {apps['response_rate']}% response rate."
        if apps["small_sample"]:
            text += " That's too few to draw firm conclusions."
        out.append({"type": "trend", "text": text, "evidence": [apps["sample_note"] or "Application tracker data"],
                    "link": "/analytics"})

    sessions = InterviewSession.query.filter_by(user_id=user.id, status="completed").all()
    scored = [s for s in sessions if s.summary and s.summary.get("scores")]
    if scored:
        dims = Counter()
        for s in scored:
            for k, v in s.summary["scores"].items():
                dims[k] += v
        weakest = min(dims, key=lambda k: dims[k])
        out.append({"type": "action", "text": f"In {len(scored)} mock interview(s), your lowest-scoring dimension is "
                                              f"{weakest.replace('_', ' ')}.",
                    "evidence": [f"Average {round(dims[weakest] / len(scored))}/100"], "link": "/interview"})
    return out


def global_search(user_id, q, limit=5):
    like = f"%{q}%"
    jobs = Job.query.filter(or_(Job.title.ilike(like), Job.company.ilike(like))).order_by(
        Job.posted_at.desc().nullslast()).limit(limit).all()
    skills = Skill.query.filter(Skill.name.ilike(like)).limit(limit).all()
    resources = (LearningResource.query.filter(LearningResource.title.ilike(like), LearningResource.is_search_link.is_(False))
                 .limit(limit).all())
    apps = Application.query.filter(Application.user_id == user_id,
                                    or_(Application.company.ilike(like), Application.position.ilike(like))).limit(limit).all()
    analyses = (AnalysisHistory.query.filter(AnalysisHistory.user_id == user_id, AnalysisHistory.target_role.ilike(like))
                .order_by(AnalysisHistory.created_at.desc()).limit(limit).all())
    return {
        "jobs": [{"id": j.id, "title": j.title, "subtitle": j.company, "link": f"/jobs?job={j.id}"} for j in jobs],
        "skills": [{"id": s.id, "title": s.name, "subtitle": s.category, "link": f"/skill-gap?skill={s.name}"} for s in skills],
        "resources": [{"id": r.id, "title": r.title, "subtitle": f"{r.platform} · {r.skill.name}", "link": r.url,
                       "external": True} for r in resources],
        "applications": [{"id": a.id, "title": f"{a.position}", "subtitle": f"{a.company} · {a.stage}", "link": "/applications"}
                         for a in apps],
        "analyses": [{"id": a.id, "title": f"Analysis: {a.target_role}", "subtitle": f"Score {a.overall_score} · {a.created_at:%d %b %Y}",
                      "link": f"/analyzer?analysis={a.id}"} for a in analyses],
    }


def admin_overview():
    """Aggregate metrics only - no access to resume content."""
    now = utcnow()
    week = now - timedelta(days=7)
    ai_rows = db.session.query(AIUsageLog.service, func.count(AIUsageLog.id),
                               func.sum(AIUsageLog.prompt_tokens + AIUsageLog.output_tokens),
                               func.sum(case((AIUsageLog.success.is_(False), 1), else_=0))).group_by(AIUsageLog.service).all()
    daily = (db.session.query(func.date(AIUsageLog.created_at), func.count(AIUsageLog.id))
             .filter(AIUsageLog.created_at >= now - timedelta(days=14)).group_by(func.date(AIUsageLog.created_at)).all())
    roles = Counter()
    for (t,) in db.session.query(Profile.target_career).filter(Profile.target_career.isnot(None)).all():
        roles[resolve_role(t) or t.strip().title()] += 1
    for (t,) in db.session.query(CareerGoal.target_role).all():
        roles[resolve_role(t) or t.strip().title()] += 1
    missing = (db.session.query(Skill.name, func.count(SkillGap.id)).join(SkillGap, SkillGap.skill_id == Skill.id)
               .filter(SkillGap.status == "missing").group_by(Skill.name).order_by(func.count(SkillGap.id).desc()).limit(10).all())
    events = Counter(dict(db.session.query(SystemEvent.category, func.count(SystemEvent.id))
                          .filter(SystemEvent.created_at >= week).group_by(SystemEvent.category).all()))
    return {
        "users": {"total": User.query.count(), "new_7d": User.query.filter(User.created_at >= week).count(),
                  "active_7d": User.query.filter(User.last_login_at >= week).count()},
        "resumes": Resume.query.count(), "resume_versions": ResumeVersion.query.count(),
        "analyses": {"total": AnalysisHistory.query.count(),
                     "last_7d": AnalysisHistory.query.filter(AnalysisHistory.created_at >= week).count()},
        "ai_usage": {"by_service": [{"service": s, "requests": int(c), "tokens": int(t or 0), "failures": int(f or 0)}
                                    for s, c, t, f in ai_rows],
                     "daily": [{"date": str(d), "requests": int(c)} for d, c in daily],
                     "total_requests": sum(int(c) for _, c, _, _ in ai_rows),
                     "total_failures": sum(int(f or 0) for _, _, _, f in ai_rows)},
        "events_7d": dict(events),
        "api_failures_7d": events.get("job_api", 0) + events.get("ai_failure", 0),
        "auth_failures_7d": events.get("auth_failure", 0),
        "top_target_roles": [{"role": r, "count": c} for r, c in roles.most_common(8)],
        "top_missing_skills": [{"skill": s, "count": int(c)} for s, c in missing],
        "recent_errors": [e.to_dict() for e in SystemEvent.query.filter(SystemEvent.level == "error")
                          .order_by(SystemEvent.created_at.desc()).limit(15)],
        "latency": latency_snapshot(),
        "jobs_stored": Job.query.count(),
    }
