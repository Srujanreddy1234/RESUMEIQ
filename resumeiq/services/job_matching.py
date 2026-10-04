"""JobMatchingService: explainable match scores between a user's profile/resume and real job postings."""
import hashlib
import json
import re
from datetime import timedelta

from sqlalchemy import or_

from ..extensions import db
from ..models import Job, JobMatch, JobSkill, Profile, SavedJob, Skill, UserSkill, utcnow
from .ats import related_skill, title_match
from .resume_service import estimate_years_experience, primary_version
from .skill_extraction import EDU_RANK, resolve_role

WEIGHTS = {"skills": 0.50, "experience": 0.15, "title": 0.15, "education": 0.10, "location": 0.10}
LEVEL_YEARS = {"entry": 0, "mid": 2, "senior": 5}


def build_user_context(user):
    profile = Profile.query.filter_by(user_id=user.id).first()
    version = primary_version(user.id)
    parsed = version.parsed_data if version else {"experience": [], "education": [], "skills": {"all": []}}
    skills = {us.skill.name: us.level for us in UserSkill.query.filter_by(user_id=user.id).all()}
    for s in parsed.get("skills", {}).get("all", []):
        skills.setdefault(s, 2)
    years = estimate_years_experience(parsed, profile.years_experience if profile else None)
    edu = max((e.get("level") or "none" for e in parsed.get("education", [])), key=lambda lv: EDU_RANK.get(lv, 0), default="none")
    target = (profile.target_career if profile else None) or ""
    ctx = {
        "skills": skills, "years": years, "education": edu, "target_role": target,
        "role_profile": resolve_role(target), "parsed": parsed, "resume_version_id": version.id if version else None,
        "work_type": profile.preferred_work_type if profile else "any",
        "salary_min": profile.salary_min if profile else None,
        "location": (profile.location or "") if profile else "",
    }
    ctx["signature"] = hashlib.sha256(json.dumps(
        [sorted(skills.items()), years, edu, target, ctx["work_type"], ctx["salary_min"], ctx["location"],
         ctx["resume_version_id"]], default=str).encode()).hexdigest()
    return ctx


def compute_match(ctx, job):
    have = set(ctx["skills"])
    required = [js.skill.name for js in job.skills if js.importance == "required"]
    preferred = [js.skill.name for js in job.skills if js.importance == "preferred"]
    matched, partial, missing = [], [], []
    num = den = 0.0
    for imp, names in (("required", required), ("preferred", preferred)):
        w = 3 if imp == "required" else 1
        for s in names:
            den += w
            if s in have:
                matched.append(s)
                num += w
            else:
                rel = related_skill(s, have)
                if rel:
                    partial.append({"skill": s, "via": rel})
                    num += w * 0.5
                else:
                    missing.append({"skill": s, "importance": imp})
    skills_score = int(100 * num / den) if den else 50

    need_years = job.experience_min_years if job.experience_min_years is not None else LEVEL_YEARS.get(job.experience_level or "", None)
    if need_years is None:
        exp_score, exp_note = 75, "Experience requirement not stated."
    elif ctx["years"] >= need_years:
        exp_score, exp_note = 100, f"Needs ~{need_years:g}+ years; you have ~{ctx['years']:g}."
    else:
        exp_score = int(max(20, 100 - (need_years - ctx["years"]) * 18))
        exp_note = f"Needs ~{need_years:g}+ years; you have ~{ctx['years']:g}."

    if not job.education_level:
        edu_score, edu_note = 85, "No degree requirement detected."
    elif EDU_RANK.get(ctx["education"], 0) >= EDU_RANK.get(job.education_level, 0):
        edu_score, edu_note = 100, f"Mentions a {job.education_level} degree; you meet it."
    else:
        edu_score, edu_note = 45, f"Mentions a {job.education_level} degree; your resume shows {ctx['education']}."

    job_role = resolve_role(job.title)
    if ctx["role_profile"] and job_role == ctx["role_profile"]:
        t_score, t_note = 100, f"Same role family as your target ({ctx['role_profile']})."
    else:
        t_score, t_note = title_match(job.title, ctx["parsed"], ctx["target_role"])

    loc_score, loc_notes = 100, []
    pref = ctx["work_type"]
    if pref and pref != "any" and job.work_type != "unknown" and job.work_type != pref:
        loc_score -= 50
        loc_notes.append(f"Job is {job.work_type}; you prefer {pref}.")
    if ctx["salary_min"] and job.salary_max and job.salary_max < ctx["salary_min"]:
        loc_score -= 40
        loc_notes.append("Listed salary is below your preferred minimum.")
    if not loc_notes:
        loc_notes.append("Fits your work-type and salary preferences (where stated).")

    comps = {"skills": skills_score, "experience": exp_score, "title": t_score, "education": edu_score, "location": max(0, loc_score)}
    score = int(round(sum(comps[k] * w for k, w in WEIGHTS.items())))
    verdict = "Strong match" if score >= 80 else "Good match" if score >= 65 else "Partial match" if score >= 45 else "Stretch role"
    why = []
    if matched:
        why.append(f"You have {len(matched)} of {len(required) + len(preferred)} listed skills ({', '.join(matched[:5])}).")
    if partial:
        why.append("Transferable: " + ", ".join(f"{p['skill']} (via {p['via']})" for p in partial[:3]) + ".")
    if missing:
        why.append("Gaps: " + ", ".join(m["skill"] for m in missing[:4]) + ".")
    if not required and not preferred:
        why.append("We couldn't extract specific skills from this posting, so the skills score is neutral.")
    return {
        "score": score, "components": comps, "matched_skills": matched, "missing_skills": missing,
        "explanation": {"verdict": verdict, "why": why, "partial": partial, "experience": exp_note,
                        "education": edu_note, "title": t_note, "location": loc_notes},
    }


def get_matches(user, ctx, jobs):
    """Return {job_id: JobMatch}, computing/refreshing stale ones."""
    if not jobs:
        return {}
    ids = [j.id for j in jobs]
    existing = {m.job_id: m for m in JobMatch.query.filter(JobMatch.user_id == user.id, JobMatch.job_id.in_(ids)).all()}
    now = utcnow()
    for job in jobs:
        m = existing.get(job.id)
        if m and m.profile_signature == ctx["signature"]:
            continue
        result = compute_match(ctx, job)
        if m is None:
            m = JobMatch(user_id=user.id, job_id=job.id)
            db.session.add(m)
            existing[job.id] = m
        m.resume_version_id = ctx["resume_version_id"]
        m.score = result["score"]
        m.skills_score = result["components"]["skills"]
        m.experience_score = result["components"]["experience"]
        m.education_score = result["components"]["education"]
        m.title_score = result["components"]["title"]
        m.location_score = result["components"]["location"]
        m.matched_skills = result["matched_skills"]
        m.missing_skills = result["missing_skills"]
        m.explanation = result["explanation"]
        m.profile_signature = ctx["signature"]
        m.computed_at = now
    db.session.flush()
    return existing


def filtered_query(user, f):
    q = Job.query
    if f.get("q"):
        for term in re.findall(r"[\w+#.]+", f["q"])[:6]:
            like = f"%{term}%"
            q = q.filter(or_(Job.title.ilike(like), Job.company.ilike(like), Job.search_terms.ilike(like)))
    if f.get("location"):
        q = q.filter(Job.location.ilike(f"%{f['location']}%"))
    if f.get("work_types"):
        q = q.filter(Job.work_type.in_(f["work_types"]))
    if f.get("salary_min"):
        q = q.filter(or_(Job.salary_max >= f["salary_min"], Job.salary_min >= f["salary_min"]))
    if f.get("experience_level"):
        q = q.filter(Job.experience_level == f["experience_level"])
    if f.get("company"):
        q = q.filter(Job.company.ilike(f"%{f['company']}%"))
    for skill_name in f.get("skills", [])[:5]:
        q = q.filter(Job.skills.any(JobSkill.skill.has(Skill.name.ilike(skill_name))))
    if f.get("posted_within"):
        q = q.filter(Job.posted_at >= utcnow() - timedelta(days=int(f["posted_within"])))
    if f.get("saved_only"):
        q = q.join(SavedJob, (SavedJob.job_id == Job.id) & (SavedJob.user_id == user.id))
    return q


def search(user, f, page=1, per_page=20, sort="match"):
    ctx = build_user_context(user)
    q = filtered_query(user, f)
    total = q.count()
    if sort == "match":
        candidates = q.order_by(Job.posted_at.desc().nullslast()).limit(300).all()
        matches = get_matches(user, ctx, candidates)
        if f.get("min_match"):
            candidates = [j for j in candidates if matches[j.id].score >= int(f["min_match"])]
            total = len(candidates)
        candidates.sort(key=lambda j: (-matches[j.id].score, -(j.posted_at.timestamp() if j.posted_at else 0)))
        page_jobs = candidates[(page - 1) * per_page: page * per_page]
    else:
        page_jobs = q.order_by(Job.posted_at.desc().nullslast()).offset((page - 1) * per_page).limit(per_page).all()
        matches = get_matches(user, ctx, page_jobs)
    saved = {s.job_id for s in SavedJob.query.filter(SavedJob.user_id == user.id,
                                                     SavedJob.job_id.in_([j.id for j in page_jobs] or [0])).all()}
    items = [dict(j.to_dict(), match=matches[j.id].to_dict(), saved=j.id in saved) for j in page_jobs]
    return {"items": items, "page": page, "per_page": per_page, "total": total,
            "pages": max(1, -(-total // per_page)), "has_resume": ctx["resume_version_id"] is not None}


def top_matches(user, limit=5):
    ctx = build_user_context(user)
    q = Job.query
    if ctx["target_role"]:
        terms = [t for t in re.findall(r"[a-zA-Z+#]+", ctx["target_role"]) if len(t) > 2][:3]
        if terms:
            q = q.filter(or_(*[Job.title.ilike(f"%{t}%") for t in terms]))
    jobs = q.order_by(Job.posted_at.desc().nullslast()).limit(150).all()
    matches = get_matches(user, ctx, jobs)
    ranked = sorted(jobs, key=lambda j: -matches[j.id].score)[:limit]
    return [dict(j.to_dict(), match=matches[j.id].to_dict()) for j in ranked], sum(1 for m in matches.values() if m.score >= 60)
