"""RoadmapService + learning tracker + ProjectRecommendationService."""
import math

from ..data.projects import PROJECTS
from ..data.resources import RESOURCES, search_links
from ..extensions import db
from ..models import (Certification, LearningProgress, LearningResource, Roadmap, RoadmapItem, Skill, UserProject, UserSkill,
                      utcnow)
from .ai import SYSTEM_GUARDRAILS, AIUnavailable, get_ai
from .ai.schemas import ProjectIdeas, RoadmapTopics
from .notifications import notify
from .skill_extraction import SKILL_BY_NAME, canonical_skill, skill_rows
from .skill_gap import compute_skill_gap

MAX_ITEMS = 8


def seed_resources():
    """Load the curated catalog (+ clearly-labelled search links) into learning_resources."""
    names = {r["skill"] for r in RESOURCES} | {s for s, meta in SKILL_BY_NAME.items() if not meta["is_soft"]}
    rows = skill_rows(sorted(names))
    existing = {(r.skill_id, r.url) for r in LearningResource.query.all()}
    curated_types = {}
    for r in RESOURCES:
        skill = rows.get(r["skill"])
        if not skill or (skill.id, r["url"]) in existing:
            continue
        curated_types.setdefault(r["skill"], set()).add(r["type"])
        db.session.add(LearningResource(skill_id=skill.id, title=r["title"], platform=r["platform"], resource_type=r["type"],
                                        difficulty=r["difficulty"], est_hours=r["est_hours"], url=r["url"],
                                        is_search_link=False, is_free=r["is_free"]))
    for name, skill in rows.items():
        for link in search_links(name):
            if (skill.id, link["url"]) in existing:
                continue
            db.session.add(LearningResource(skill_id=skill.id, title=link["title"], platform=link["platform"],
                                            resource_type=link["type"], difficulty="beginner", est_hours=None,
                                            url=link["url"], is_search_link=True, is_free=link["is_free"]))
    db.session.flush()


def _topological(items):
    names = {i["skill"] for i in items}
    ordered, seen = [], set()

    def visit(item, stack=()):
        if item["skill"] in seen or item["skill"] in stack:
            return
        for pre in item.get("prerequisites", []):
            if pre in names:
                visit(next(i for i in items if i["skill"] == pre), stack + (item["skill"],))
        seen.add(item["skill"])
        ordered.append(item)

    for item in items:
        visit(item)
    return ordered


def _projects_for(skill):
    return [p["title"] for p in PROJECTS if skill in p["skills"]][:2]


def generate_roadmap(user_id, target_role, weekly_hours=8):
    gap = compute_skill_gap(user_id, target_role)
    todo = [i for i in gap["items"] if i["status"] != "strong"][:MAX_ITEMS]
    ordered = _topological(todo)

    missing_topics = [i["skill"] for i in ordered if not SKILL_BY_NAME.get(i["skill"], {}).get("topics")]
    ai_topics, ai_note = {}, None
    if missing_topics and get_ai().available_for(user_id):
        try:
            res = get_ai().generate(
                service="roadmap_topics", user_id=user_id, schema=RoadmapTopics, system=SYSTEM_GUARDRAILS, temperature=0.2,
                prompt=f"For a person targeting '{target_role}', list 4-6 concrete sub-topics to learn for each skill: "
                       f"{', '.join(missing_topics)}. Return items with skill and topics. No URLs.")
            ai_topics = {canonical_skill(i.skill) or i.skill: i.topics[:6] for i in res.items}
        except AIUnavailable as exc:
            ai_note = exc.user_message

    Roadmap.query.filter_by(user_id=user_id, is_active=True).update({"is_active": False})
    total_hours = 0
    roadmap = Roadmap(user_id=user_id, target_role=target_role[:120], weekly_hours=max(1, int(weekly_hours or 8)), is_active=True)
    db.session.add(roadmap)
    db.session.flush()
    rows = skill_rows([i["skill"] for i in ordered], create_unknown=True)
    user_skills = {us.skill.name for us in UserSkill.query.filter_by(user_id=user_id).all()}
    for pos, item in enumerate(ordered):
        meta = SKILL_BY_NAME.get(item["skill"], {})
        hours = int(item["est_hours"] * (0.5 if item["status"] == "needs_improvement" else 1))
        total_hours += hours
        topics = meta.get("topics") or ai_topics.get(item["skill"]) or [f"Core concepts of {item['skill']}",
                                                                          f"Hands-on practice with {item['skill']}"]
        prereqs = [{"skill": p, "have": p in user_skills} for p in meta.get("prerequisites", [])]
        why = "; ".join(item["evidence"]) or "Identified as a gap for your target role."
        if item.get("unlocks"):
            why += f". Unlocks: {', '.join(item['unlocks'])}"
        db.session.add(RoadmapItem(roadmap_id=roadmap.id, skill_id=rows[item["skill"]].id, phase=pos + 1, position=pos,
                                   what_to_learn=topics, why=why, prerequisites=prereqs,
                                   project_ideas=_projects_for(item["skill"]), est_hours=hours))
    weeks = math.ceil(total_hours / roadmap.weekly_hours) if total_hours else 0
    roadmap.summary = (f"{len(ordered)} skill(s), about {total_hours} hours - roughly {weeks} week(s) at "
                       f"{roadmap.weekly_hours} h/week." if ordered else "No gaps found against the current requirements.")
    db.session.flush()
    return roadmap, ai_note


def _resource_progress(user_id, resource_ids):
    if not resource_ids:
        return {}
    return {p.resource_id: p for p in LearningProgress.query.filter(
        LearningProgress.user_id == user_id, LearningProgress.resource_id.in_(resource_ids)).all()}


def roadmap_view(user_id, roadmap):
    skill_ids = [i.skill_id for i in roadmap.items]
    resources = LearningResource.query.filter(LearningResource.skill_id.in_(skill_ids or [0])).all()
    progress = _resource_progress(user_id, [r.id for r in resources])
    by_skill = {}
    for r in resources:
        by_skill.setdefault(r.skill_id, []).append(r)
    items, done_hours, total_hours = [], 0.0, 0
    for it in roadmap.items:
        res = by_skill.get(it.skill_id, [])
        res_dicts = [dict(r.to_dict(), status=progress[r.id].status if r.id in progress else "not_started",
                          hours_spent=progress[r.id].hours_spent if r.id in progress else 0) for r in res]
        curated = [r for r in res_dicts if not r["is_search_link"]]
        completed = sum(1 for r in curated if r["status"] == "completed")
        if it.status == "completed":
            frac = 1.0
        elif curated:
            frac = min(0.9, completed / len(curated)) if it.status == "in_progress" or completed else 0
        else:
            frac = 0.5 if it.status == "in_progress" else 0
        total_hours += it.est_hours
        done_hours += it.est_hours * frac
        items.append({
            "id": it.id, "phase": it.phase, "skill": it.skill.to_dict(), "status": it.status,
            "what_to_learn": it.what_to_learn, "why": it.why, "prerequisites": it.prerequisites,
            "project_ideas": it.project_ideas, "est_hours": it.est_hours, "progress": round(frac * 100),
            "resources": {"beginner": [r for r in res_dicts if r["difficulty"] == "beginner"],
                          "intermediate": [r for r in res_dicts if r["difficulty"] != "beginner"]},
        })
    return {"id": roadmap.id, "target_role": roadmap.target_role, "weekly_hours": roadmap.weekly_hours,
            "summary": roadmap.summary, "created_at": roadmap.created_at.isoformat(), "items": items,
            "progress": round(100 * done_hours / total_hours) if total_hours else 0,
            "estimated_weeks": math.ceil(total_hours / roadmap.weekly_hours) if total_hours else 0}


def active_roadmap(user_id):
    return Roadmap.query.filter_by(user_id=user_id, is_active=True).order_by(Roadmap.created_at.desc()).first()


def set_item_status(user_id, item, status):
    item.status = status
    if status == "completed":
        us = UserSkill.query.filter_by(user_id=user_id, skill_id=item.skill_id).first()
        if us is None:
            db.session.add(UserSkill(user_id=user_id, skill_id=item.skill_id, level=2, source="learning"))
        elif us.level < 2:
            us.level = 2
    db.session.flush()
    roadmap = db.session.get(Roadmap, item.roadmap_id)
    pct = roadmap_view(user_id, roadmap)["progress"]
    for milestone in (25, 50, 75, 100):
        if pct >= milestone:
            notify(user_id, "learning", f"Learning milestone: {milestone}% of your {roadmap.target_role} roadmap",
                   "Keep going - consistent practice compounds.", "/roadmap", dedupe_key=f"roadmap-{roadmap.id}-{milestone}")


def set_resource_progress(user_id, resource, status, hours=None):
    p = LearningProgress.query.filter_by(user_id=user_id, resource_id=resource.id).first()
    if p is None:
        p = LearningProgress(user_id=user_id, resource_id=resource.id, status="not_started", hours_spent=0)
        db.session.add(p)
    now = utcnow()
    if status in ("in_progress", "completed") and p.started_at is None:
        p.started_at = now
    p.completed_at = now if status == "completed" else None
    p.status = status
    if hours is not None:
        p.hours_spent = max(0.0, min(1000.0, float(hours)))
    elif status == "completed" and not p.hours_spent and resource.est_hours:
        p.hours_spent = float(resource.est_hours)
    db.session.flush()
    return p


def learning_stats(user_id):
    progress = LearningProgress.query.filter_by(user_id=user_id).all()
    roadmap = active_roadmap(user_id)
    view = roadmap_view(user_id, roadmap) if roadmap else None
    certs = Certification.query.filter_by(user_id=user_id).all()
    return {
        "skills_completed": sum(1 for i in (view["items"] if view else []) if i["status"] == "completed"),
        "skills_total": len(view["items"]) if view else 0,
        "hours_learned": round(sum(p.hours_spent for p in progress), 1),
        "courses_completed": sum(1 for p in progress if p.status == "completed" and p.resource.resource_type == "course"),
        "resources_completed": sum(1 for p in progress if p.status == "completed"),
        "resources_in_progress": sum(1 for p in progress if p.status == "in_progress"),
        "projects_completed": UserProject.query.filter_by(user_id=user_id, source="roadmap").count(),
        "certifications": {"earned": sum(1 for c in certs if c.status == "earned"),
                           "in_progress": sum(1 for c in certs if c.status == "in_progress")},
        "roadmap_progress": view["progress"] if view else None,
        "roadmap_role": roadmap.target_role if roadmap else None,
        "timeline": _completion_timeline(progress),
    }


def _completion_timeline(progress):
    buckets = {}
    for p in progress:
        if p.completed_at:
            key = p.completed_at.strftime("%Y-%m")
            buckets[key] = buckets.get(key, 0) + 1
    return [{"month": k, "completed": v} for k, v in sorted(buckets.items())]


# ── Project recommendations ──────────────────────────────────────────────
def recommend_projects(user_id, target_role, limit=5):
    gap = compute_skill_gap(user_id, target_role, persist=False)
    missing = [i["skill"] for i in gap["items"] if i["status"] != "strong"]
    have = {i["skill"] for i in gap["items"] if i["status"] == "strong"} | {
        us.skill.name for us in UserSkill.query.filter_by(user_id=user_id).all()}
    scored = []
    for p in PROJECTS:
        learn = [s for s in p["skills"] if s in missing]
        known = [s for s in p["skills"] + p["alt_skills"] if s in have]
        if not learn:
            continue
        scored.append((len(learn) * 3 + len(known), p, learn))
    scored.sort(key=lambda x: -x[0])
    out = [_project_view(p, learn) for _, p, learn in scored[:limit]]

    ai_note = None
    if missing and get_ai().available_for(user_id):
        try:
            res = get_ai().generate(
                service="project_recommendation", user_id=user_id, schema=ProjectIdeas, system=SYSTEM_GUARDRAILS,
                temperature=0.6,
                prompt=f"Target role: {target_role}. Skills the user already has: {', '.join(sorted(have)[:25]) or 'few'}. "
                       f"Skills to learn (priority order): {', '.join(missing[:8])}. Suggest 3 portfolio projects that "
                       "combine 2-4 of the skills to learn with skills they have. Be specific and realistic. No URLs.")
            for idea in res.projects[:3]:
                skills = [canonical_skill(s) for s in idea.skills]
                skills = [s for s in skills if s]
                learn = [s for s in skills if s in missing]
                if not learn:
                    continue
                out.append(_project_view({"title": idea.title, "difficulty": idea.difficulty, "skills": skills,
                                          "alt_skills": [], "features": idea.features[:8],
                                          "duration_weeks": idea.duration_weeks, "resume_value": idea.resume_value},
                                         learn, ai=True, technologies=idea.technologies))
        except AIUnavailable as exc:
            ai_note = exc.user_message
    return {"target_role": target_role, "missing_skills": missing[:10], "projects": out, "ai_note": ai_note}


def _project_view(p, learn, ai=False, technologies=None):
    skill_ids = [s.id for s in Skill.query.filter(Skill.name.in_(learn)).all()]
    resources = (LearningResource.query.filter(LearningResource.skill_id.in_(skill_ids or [0]),
                                               LearningResource.is_search_link.is_(False)).limit(6).all())
    return {"title": p["title"], "difficulty": p["difficulty"], "skills_learned": learn,
            "technologies": sorted(set(technologies or []) | set(p["skills"])), "features": p["features"],
            "duration_weeks": p["duration_weeks"], "resume_value": p["resume_value"], "ai_generated": ai,
            "resources": [r.to_dict() for r in resources]}
