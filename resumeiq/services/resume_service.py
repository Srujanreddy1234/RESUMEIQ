"""ResumeAnalysisService: resume storage/versioning, structured extraction and scoring."""
import logging
import re
from datetime import date

from ..errors import ApiError, Conflict
from ..extensions import db
from ..models import (AnalysisHistory, Certification, Education, Experience, Profile, Resume, ResumeSkill, ResumeVersion,
                      UserProject, UserSkill, utcnow)
from . import storage
from .ai import SYSTEM_GUARDRAILS, AIUnavailable, get_ai
from .ai.schemas import ResumeExtraction, ResumeFeedback
from .notifications import notify
from .resume_parser import merge_ai_extraction, parse_resume
from .scoring import score_resume, strengths_and_weaknesses
from .skill_extraction import role_requirements, skill_rows
from .text_extraction import extract_text

log = logging.getLogger(__name__)
MAX_PROMPT_CHARS = 14000


# ── Upload & versioning ──────────────────────────────────────────────────
def upload_resume(user, file_storage, name=None, resume_id=None, max_resumes=20):
    data, ext, mime = storage.read_upload(file_storage, "resume")
    text = extract_text(data, ext)  # validate readability before anything is stored

    if resume_id:
        resume = Resume.query.filter_by(id=resume_id, user_id=user.id).first()
        if resume is None:
            raise ApiError("Resume not found.", status=404, code="not_found")
    else:
        if Resume.query.filter_by(user_id=user.id).count() >= max_resumes:
            raise ApiError(f"You can store up to {max_resumes} resumes. Delete one to upload another.",
                           status=400, code="resume_limit")
        default_name = re.sub(r"\.[A-Za-z0-9]+$", "", file_storage.filename or "Resume")[:100] or "Resume"
        resume = Resume(user_id=user.id, name=(name or default_name).strip()[:120],
                        is_primary=Resume.query.filter_by(user_id=user.id).count() == 0)
        db.session.add(resume)
        db.session.flush()

    stored_name, checksum = storage.save_bytes(data, ext)
    if any(v.checksum == checksum for v in resume.versions):
        storage.delete_file(stored_name)
        raise Conflict("This exact file is already uploaded as a version of this resume.")

    version = ResumeVersion(
        resume_id=resume.id, version_number=(resume.latest_version.version_number + 1 if resume.versions else 1),
        original_filename=_safe_display_name(file_storage.filename), stored_filename=stored_name, file_type=ext,
        mime_type=mime, file_size=len(data), checksum=checksum, extracted_text=text,
    )
    db.session.add(version)
    db.session.flush()
    apply_parse(version, parse_resume(text), "heuristic")
    resume.updated_at = utcnow()
    if resume.is_primary:
        sync_profile_from_resume(user.id, version)
    return resume, version


def _safe_display_name(filename):
    name = re.sub(r"[^\w.\- ()]+", "_", filename or "resume")
    return name[-200:]


def apply_parse(version, parsed, method):
    version.parsed_data = parsed
    version.parse_method = method
    version.word_count = parsed.get("word_count", 0)
    ResumeSkill.query.filter_by(resume_version_id=version.id).delete()
    rows = skill_rows(parsed["skills"]["all"], create_unknown=True)
    mentions = parsed["skills"].get("mentions", {})
    for name, skill in rows.items():
        db.session.add(ResumeSkill(resume_version_id=version.id, skill_id=skill.id,
                                   source="ai" if method == "ai" else "taxonomy", mentions=int(mentions.get(name, 1))))
    db.session.flush()


def estimate_level(skill, parsed):
    """Rough proficiency estimate from resume evidence (self-assessment can override)."""
    level = 2
    exp_text = " ".join(b for e in parsed["experience"] for b in e.get("bullets", [])).lower()
    proj_tech = {t for p in parsed["projects"] for t in p.get("technologies", [])}
    if skill.lower() in exp_text:
        level += 1
    if skill in proj_tech:
        level += 0.5
    if parsed["skills"].get("mentions", {}).get(skill, 1) >= 3:
        level += 0.5
    return int(min(4, level))


def sync_profile_from_resume(user_id, version):
    """Populate career-profile tables from the primary resume (manual entries are never touched)."""
    parsed = version.parsed_data or {}
    for model in (Education, Experience, UserProject):
        model.query.filter_by(user_id=user_id, source="resume").delete()
    Certification.query.filter_by(user_id=user_id, source="resume").delete()
    for e in parsed.get("education", [])[:6]:
        if e.get("institution"):
            db.session.add(Education(user_id=user_id, institution=e["institution"][:200], degree=(e.get("degree") or "")[:160] or None,
                                     field_of_study=(e.get("field_of_study") or "")[:160] or None,
                                     graduation_year=e.get("graduation_year"), gpa=(e.get("gpa") or "")[:20] or None, source="resume"))
    for x in parsed.get("experience", [])[:12]:
        if x.get("company"):
            db.session.add(Experience(user_id=user_id, company=x["company"][:200], title=(x.get("title") or "")[:160] or None,
                                      kind=x.get("kind") or "job", start_date=(x.get("start_date") or "")[:20] or None,
                                      end_date=(x.get("end_date") or "")[:20] or None,
                                      description="\n".join(x.get("bullets", []))[:4000], source="resume"))
    for p in parsed.get("projects", [])[:12]:
        db.session.add(UserProject(user_id=user_id, name=(p.get("name") or "Project")[:200],
                                   description=(p.get("description") or "")[:4000], technologies=p.get("technologies", []),
                                   source="resume"))
    for c in parsed.get("certifications", [])[:15]:
        db.session.add(Certification(user_id=user_id, name=c[:200], status="earned", source="resume"))

    rows = skill_rows(parsed.get("skills", {}).get("all", []))
    existing = {us.skill_id: us for us in UserSkill.query.filter_by(user_id=user_id).all()}
    for name, skill in rows.items():
        level = estimate_level(name, parsed)
        current = existing.get(skill.id)
        if current is None:
            db.session.add(UserSkill(user_id=user_id, skill_id=skill.id, level=level, source="resume"))
        elif current.source == "resume" and level > current.level:
            current.level = level

    profile = Profile.query.filter_by(user_id=user_id).first()
    if profile and not profile.education_summary and parsed.get("education"):
        e = parsed["education"][0]
        profile.education_summary = ", ".join(filter(None, [e.get("degree"), e.get("institution")]))[:255] or None
    if profile and not profile.github_url and parsed.get("contact", {}).get("github"):
        profile.github_url = parsed["contact"]["github"][:255]
    if profile and not profile.linkedin_url and parsed.get("contact", {}).get("linkedin"):
        profile.linkedin_url = parsed["contact"]["linkedin"][:255]
    db.session.flush()


def set_primary(user_id, resume):
    Resume.query.filter_by(user_id=user_id).update({"is_primary": False})
    resume.is_primary = True
    if resume.latest_version:
        sync_profile_from_resume(user_id, resume.latest_version)


def delete_resume(user_id, resume):
    files = [v.stored_filename for v in resume.versions]
    was_primary = resume.is_primary
    db.session.delete(resume)
    db.session.flush()
    for f in files:
        storage.delete_file(f)
    if was_primary:
        nxt = Resume.query.filter_by(user_id=user_id).order_by(Resume.updated_at.desc()).first()
        if nxt:
            set_primary(user_id, nxt)


def primary_version(user_id):
    resume = Resume.query.filter_by(user_id=user_id, is_primary=True).first() \
        or Resume.query.filter_by(user_id=user_id).order_by(Resume.updated_at.desc()).first()
    return resume.latest_version if resume else None


# ── AI extraction ────────────────────────────────────────────────────────
def ai_extract(version, user_id):
    """Structured extraction with Gemini, grounded against the text. Raises AIUnavailable."""
    prompt = (
        "Extract structured information from this resume. Only include information that is explicitly present. "
        "Classify each experience as 'job' or 'internship'. Keep bullets verbatim.\n\n"
        f"<resume>\n{version.extracted_text[:MAX_PROMPT_CHARS]}\n</resume>"
    )
    result = get_ai().generate(service="resume_extraction", prompt=prompt, schema=ResumeExtraction,
                               user_id=user_id, temperature=0.1, system=SYSTEM_GUARDRAILS)
    if not result.is_meaningful():
        raise AIUnavailable("invalid_response")
    heuristic = parse_resume(version.extracted_text)
    return merge_ai_extraction(heuristic, result, version.extracted_text)


# ── Analysis pipeline ────────────────────────────────────────────────────
ANALYSIS_STAGES = [("read", "Reading document"), ("extract", "Extracting structure & skills"),
                   ("compare", "Comparing against role requirements"), ("score", "Scoring resume"),
                   ("insights", "Generating AI feedback"), ("save", "Saving results")]


def run_analysis(ctx, user_id, version_id, target_role, job_description_id=None):
    from ..models import JobDescription
    ctx.stage("read")
    version = db.session.get(ResumeVersion, version_id)
    if version is None or version.resume.user_id != user_id:
        raise ApiError("Resume not found.", status=404, code="not_found")
    ai = get_ai()

    ctx.stage("extract")
    ai_note = None
    if version.parse_method != "ai":
        if ai.available_for(user_id):
            try:
                apply_parse(version, ai_extract(version, user_id), "ai")
            except AIUnavailable as exc:
                ai_note = exc.user_message + " Used the built-in parser instead."
        else:
            ai_note = ("AI extraction unavailable (" + ("not configured" if not ai.configured else "daily limit reached")
                       + "); used the built-in parser.")
    parsed = version.parsed_data

    ctx.stage("compare")
    role_name, requirements = role_requirements(target_role, parsed["skills"]["all"])
    jd = db.session.get(JobDescription, job_description_id) if job_description_id else None
    if jd is not None and jd.user_id != user_id:
        jd = None
    keyword_reqs = None
    if jd is not None:
        keyword_reqs = ([{"skill": s, "importance": "required"} for s in jd.parsed.get("required_skills", [])]
                        + [{"skill": s, "importance": "preferred"} for s in jd.parsed.get("preferred_skills", [])])

    ctx.stage("score")
    scored = score_resume(parsed, version.extracted_text, version.file_type, role_name, requirements, keyword_reqs)
    strengths, weaknesses = strengths_and_weaknesses(scored["components"])
    have = set(parsed["skills"]["all"])
    reqs = keyword_reqs or requirements
    matched = sorted({r["skill"] for r in reqs if r["skill"] in have})
    missing = sorted({r["skill"] for r in reqs if r["skill"] not in have})

    ctx.stage("insights")
    ai_feedback = None
    if ai.available_for(user_id):
        try:
            ai_feedback = _ai_feedback(version, parsed, scored, target_role, user_id).model_dump()
        except AIUnavailable as exc:
            ai_note = (ai_note + " " if ai_note else "") + exc.user_message + " Showing rule-based feedback only."
    else:
        ctx.skip("insights", "AI unavailable - rule-based feedback shown")

    ctx.stage("save")
    analysis = AnalysisHistory(
        user_id=user_id, resume_version_id=version.id, job_description_id=jd.id if jd else None,
        kind="jd_match" if jd else "resume", target_role=target_role[:120], overall_score=scored["overall"],
        score_breakdown=scored["components"], skills_identified=len(have), ai_used=bool(ai_feedback) or version.parse_method == "ai",
        result={
            "grade": scored["grade"], "strengths": strengths, "weaknesses": weaknesses, "ai_feedback": ai_feedback,
            "ai_note": ai_note, "role_profile": role_name, "matched_skills": matched, "missing_skills": missing,
            "skills": parsed["skills"]["by_category"], "all_skills": parsed["skills"]["all"],
            "contact": {k: bool(v) for k, v in parsed["contact"].items() if k != "links"},
            "parse_method": version.parse_method, "word_count": parsed["word_count"],
            "candidate_name": parsed["contact"].get("name"),
        },
    )
    db.session.add(analysis)
    version.latest_score = scored["overall"]
    version.last_analyzed_at = utcnow()
    if version.resume.is_primary:
        sync_profile_from_resume(user_id, version)
    db.session.flush()
    notify(user_id, "analysis", f"Resume analysis complete: {scored['overall']}/100",
           f"{version.resume.name} v{version.version_number} for {target_role}.", f"/analyzer?analysis={analysis.id}",
           dedupe_key=f"analysis-{analysis.id}")
    return {"analysis_id": analysis.id, "score": scored["overall"]}


def _ai_feedback(version, parsed, scored, target_role, user_id):
    rubric = "\n".join(f"- {c['label']}: {c['score']}/100 — {c['explanation']}" for c in scored["components"])
    prompt = (
        f"Target role: {target_role}\n\nOur transparent rubric already scored this resume (do NOT change the numbers):\n"
        f"{rubric}\n\nWrite qualitative feedback consistent with the rubric: a 2-3 sentence summary, up to 4 strengths, "
        "up to 4 weaknesses, and per-section comments (summary, experience, projects, skills, education). Reference "
        "specific content from the resume. Do not invent achievements or numbers.\n\n"
        f"<resume>\n{version.extracted_text[:MAX_PROMPT_CHARS]}\n</resume>"
    )
    return get_ai().generate(service="resume_feedback", prompt=prompt, schema=ResumeFeedback, user_id=user_id,
                             temperature=0.3, system=SYSTEM_GUARDRAILS)


# ── Version comparison ───────────────────────────────────────────────────
def compare_versions(a, b):
    """Compare two ResumeVersions (a = older, b = newer)."""
    from .resume_parser import has_metric
    pa, pb = a.parsed_data or {}, b.parsed_data or {}
    sa, sb = set(pa.get("skills", {}).get("all", [])), set(pb.get("skills", {}).get("all", []))
    ba = {x["text"] for x in pa.get("bullets", [])}
    bb = {x["text"] for x in pb.get("bullets", [])}
    new_bullets = sorted(bb - ba)
    removed_bullets = sorted(ba - bb)
    metrics_a = sum(1 for t in ba if has_metric(t))
    metrics_b = sum(1 for t in bb if has_metric(t))
    return {
        "from": a.to_dict(), "to": b.to_dict(),
        "score_change": (b.latest_score - a.latest_score) if a.latest_score is not None and b.latest_score is not None else None,
        "added_skills": sorted(sb - sa), "removed_skills": sorted(sa - sb),
        "added_bullets": new_bullets[:30], "removed_bullets": removed_bullets[:30],
        "bullets_with_metrics": {"from": metrics_a, "to": metrics_b},
        "added_metrics": max(0, metrics_b - metrics_a),
        "word_count": {"from": pa.get("word_count"), "to": pb.get("word_count")},
        "sections_added": sorted(set(pb.get("sections_found", [])) - set(pa.get("sections_found", []))),
        "sections_removed": sorted(set(pa.get("sections_found", [])) - set(pb.get("sections_found", []))),
        "projects": {"from": len(pa.get("projects", [])), "to": len(pb.get("projects", []))},
        "experience": {"from": len(pa.get("experience", [])), "to": len(pb.get("experience", []))},
    }


def estimate_years_experience(parsed, profile_years=None):
    """Estimate professional experience in years from experience date ranges (internships count half)."""
    if profile_years is not None:
        return float(profile_years)
    months = 0
    now = date.today()
    month_names = "jan feb mar apr may jun jul aug sep oct nov dec".split()

    def parse(value, default_month):
        if not value:
            return None
        v = value.lower()
        if any(k in v for k in ("present", "current", "now")):
            return now.year, now.month
        year = re.search(r"(19|20)\d{2}", v)
        if not year:
            return None
        month = next((i + 1 for i, m in enumerate(month_names) if m in v), default_month)
        return int(year.group(0)), month

    for e in parsed.get("experience", []):
        start, end = parse(e.get("start_date"), 1), parse(e.get("end_date"), 12)
        if start and not end:
            end = start
        if start and end:
            span = max(1, (end[0] - start[0]) * 12 + end[1] - start[1] + 1)
            months += span * (0.5 if e.get("kind") == "internship" else 1)
    return round(months / 12, 1)
