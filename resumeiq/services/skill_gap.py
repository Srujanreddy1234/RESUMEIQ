"""Skill-gap engine.

Requirements come from three sources, each recorded as evidence:
  1. Curated role baseline (data/taxonomy.py ROLE_PROFILES)
  2. Frequency across real job postings stored in the DB (only reported when the sample is large enough)
  3. Job descriptions the user has analysed for this role
We never claim a skill is universally required: the evidence shows exactly why it is listed.
"""
from collections import Counter

from sqlalchemy import func

from ..extensions import db
from ..models import Job, JobDescription, JobSkill, LearningProgress, LearningResource, Skill, SkillGap, UserSkill, utcnow
from .skill_extraction import SKILL_BY_NAME, SOFT_SKILL_NAMES, resolve_role, role_requirements, skill_rows

MIN_JOB_SAMPLE = 5
IMPORTANCE_W = {"core": 40, "important": 25, "nice": 10}
RANK = {"nice": 1, "important": 2, "core": 3}


def _role_jobs(role_name, limit=300):
    """Recent stored postings whose title maps to the same role profile."""
    jobs = Job.query.order_by(Job.posted_at.desc().nullslast()).limit(2000).all()
    return [j for j in jobs if resolve_role(j.title) == role_name][:limit]


def job_frequencies(role_name):
    jobs = _role_jobs(role_name)
    if not jobs:
        return 0, {}
    ids = [j.id for j in jobs]
    rows = (db.session.query(Skill.name, func.count(JobSkill.id))
            .join(JobSkill, JobSkill.skill_id == Skill.id)
            .filter(JobSkill.job_id.in_(ids)).group_by(Skill.name).all())
    return len(jobs), {name: count / len(jobs) for name, count in rows}


def compute_skill_gap(user_id, target_role, persist=True):
    user_skills = {us.skill.name: us.level for us in UserSkill.query.filter_by(user_id=user_id).all()}
    role_name, curated = role_requirements(target_role, user_skills.keys())
    sample, freqs = job_frequencies(role_name) if role_name else (0, {})
    use_freq = sample >= MIN_JOB_SAMPLE

    reqs = {}
    for r in curated:
        reqs[r["skill"]] = {"importance": r["importance"], "level": r["level"],
                            "evidence": [f"{r['importance'].capitalize()} skill in our curated {role_name} baseline"
                                         + (f" (any of: {', '.join(r['alternatives'])})" if r.get("alternatives") else "")]}

    if use_freq:
        for skill, f in freqs.items():
            if skill in SOFT_SKILL_NAMES or f < 0.15:
                continue
            imp = "core" if f >= 0.5 else "important" if f >= 0.25 else "nice"
            entry = reqs.setdefault(skill, {"importance": imp, "level": 3 if imp == "core" else 2, "evidence": []})
            if RANK[imp] > RANK[entry["importance"]]:
                entry["importance"] = imp
            entry["evidence"].append(f"Mentioned in {round(f * 100)}% of {sample} stored {role_name} postings")

    jds = [jd for jd in JobDescription.query.filter_by(user_id=user_id).order_by(JobDescription.created_at.desc()).limit(20)
           if resolve_role(jd.title) == role_name or (jd.title or "").lower() == (target_role or "").lower()]
    jd_counter = Counter(s for jd in jds for s in jd.parsed.get("required_skills", []))
    for skill, count in jd_counter.items():
        entry = reqs.setdefault(skill, {"importance": "important", "level": 3, "evidence": []})
        entry["evidence"].append(f"Required in {count} job description(s) you analysed")

    if not reqs:
        return {"target_role": target_role, "role_profile": None, "items": [], "readiness": None,
                "data_note": "We don't have a curated baseline for this role yet. Analyse a job description for it to "
                             "build requirements from real postings."}

    missing_names = {s for s in reqs if user_skills.get(s, 0) == 0}
    items = []
    for skill, r in reqs.items():
        current = user_skills.get(skill, 0)
        required = r["level"]
        status = "strong" if current >= required else ("needs_improvement" if current > 0 else "missing")
        meta = SKILL_BY_NAME.get(skill, {})
        difficulty = meta.get("difficulty", 2)
        unlocks = [s for s in missing_names if skill in SKILL_BY_NAME.get(s, {}).get("prerequisites", [])]
        priority = 0.0
        if status != "strong":
            priority = (IMPORTANCE_W[r["importance"]] + (freqs.get(skill, 0) * 30 if use_freq else 0)
                        + (required - current) * 8 - difficulty * 4 + 5 * len(unlocks))
        items.append({"skill": skill, "status": status, "current_level": current, "required_level": required,
                      "importance": r["importance"], "job_frequency": round(freqs[skill], 3) if use_freq and skill in freqs else None,
                      "priority_score": round(priority, 1), "difficulty": difficulty, "unlocks": unlocks,
                      "prerequisites": [p for p in meta.get("prerequisites", [])],
                      "evidence": r["evidence"], "est_hours": meta.get("est_hours", 15),
                      "category": meta.get("category", "other")})

    gaps = sorted((i for i in items if i["status"] != "strong"), key=lambda i: (-i["priority_score"], i["skill"]))
    for rank, item in enumerate(gaps, 1):
        item["priority_rank"] = rank
    total_w = sum(IMPORTANCE_W[i["importance"]] for i in items)
    readiness = round(100 * sum(IMPORTANCE_W[i["importance"]] * min(1, i["current_level"] / i["required_level"])
                                for i in items) / total_w) if total_w else None

    if persist:
        SkillGap.query.filter_by(user_id=user_id, target_role=target_role[:120]).delete()
        rows = skill_rows([i["skill"] for i in items], create_unknown=True)
        now = utcnow()
        seen = set()
        for i in items:
            if i["skill"] in rows and rows[i["skill"]].id not in seen:
                seen.add(rows[i["skill"]].id)
                db.session.add(SkillGap(user_id=user_id, skill_id=rows[i["skill"]].id, target_role=target_role[:120],
                                        status=i["status"], current_level=i["current_level"], required_level=i["required_level"],
                                        importance=i["importance"], job_frequency=i["job_frequency"],
                                        priority_score=i["priority_score"], priority_rank=i.get("priority_rank"),
                                        evidence=i["evidence"], computed_at=now))
        db.session.flush()

    note = (f"Job-frequency data from {sample} stored postings for {role_name}." if use_freq else
            f"Only {sample} stored posting(s) match this role, so we rely on the curated baseline"
            + (" and your analysed job descriptions" if jds else "") + ". Search jobs to add market evidence.")
    return {"target_role": target_role, "role_profile": role_name, "readiness": readiness, "job_sample": sample,
            "data_note": note, "items": sorted(items, key=lambda i: (i["status"] == "strong", -i["priority_score"], i["skill"]))}


def skill_detail(user_id, skill_name, target_role=None):
    skill = Skill.query.filter_by(name=skill_name).first()
    if skill is None:
        return None
    us = UserSkill.query.filter_by(user_id=user_id, skill_id=skill.id).first()
    gap = None
    if target_role:
        gap = SkillGap.query.filter_by(user_id=user_id, skill_id=skill.id, target_role=target_role[:120]).first()
    resources = LearningResource.query.filter_by(skill_id=skill.id).order_by(
        LearningResource.is_search_link, LearningResource.difficulty).all()
    progress = {p.resource_id: p for p in LearningProgress.query.filter(
        LearningProgress.user_id == user_id, LearningProgress.resource_id.in_([r.id for r in resources] or [0])).all()}
    job_count = db.session.query(func.count(JobSkill.id)).filter(JobSkill.skill_id == skill.id).scalar()
    sample_jobs = (Job.query.join(JobSkill, JobSkill.job_id == Job.id).filter(JobSkill.skill_id == skill.id)
                   .order_by(Job.posted_at.desc().nullslast()).limit(5).all())
    completed = sum(1 for p in progress.values() if p.status == "completed")
    meta = SKILL_BY_NAME.get(skill.name, {})
    return {
        "skill": skill.to_dict(), "topics": meta.get("topics", []), "prerequisites": meta.get("prerequisites", []),
        "current_level": us.level if us else 0, "level_source": us.source if us else None,
        "required_level": gap.required_level if gap else None, "status": gap.status if gap else None,
        "evidence": gap.evidence if gap else [],
        "resources": [dict(r.to_dict(), status=progress[r.id].status if r.id in progress else "not_started") for r in resources],
        "jobs_requiring": {"count": job_count, "examples": [j.to_dict() for j in sample_jobs]},
        "learning_progress": {"completed": completed, "total": len([r for r in resources if not r.is_search_link]),
                              "hours": round(sum(p.hours_spent for p in progress.values()), 1)},
    }
