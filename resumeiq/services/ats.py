"""ATS analyzer: resume vs. job description comparison with MATCHED / PARTIAL / MISSING / NOT RELEVANT."""
import re

from ..data.taxonomy import ROLE_PROFILES
from .resume_service import estimate_years_experience
from .scoring import score_ats
from .skill_extraction import EDU_RANK, SKILL_BY_NAME, SOFT_SKILL_NAMES, extract_education_level

RELATED_GROUPS = [
    {"PostgreSQL", "MySQL", "SQL Server", "Oracle Database", "SQLite"},
    {"MongoDB", "Cassandra", "DynamoDB", "Firebase"},
    {"AWS", "Azure", "Google Cloud"},
    {"React", "Angular", "Vue.js", "Svelte", "Next.js"},
    {"Django", "Flask", "FastAPI"},
    {"Spring Boot", "Spring Framework", "Hibernate"},
    {"Express.js", "Node.js"},
    {"Jest", "pytest", "JUnit", "Unit Testing"},
    {"TensorFlow", "PyTorch", "Deep Learning"},
    {"Tableau", "Power BI", "Data Visualization"},
    {"Docker", "Kubernetes"},
    {"Kafka", "RabbitMQ"},
    {"Java", "Kotlin", "Scala"},
    {"JavaScript", "TypeScript"},
    {"C++", "C"},
    {"Terraform", "Ansible"},
    {"ETL", "Airflow", "Data Warehousing"},
    {"Android", "iOS", "Flutter", "React Native"},
]


def related_skill(skill, have):
    """Return a skill the user has that is closely related to `skill`, or None."""
    for group in RELATED_GROUPS:
        if skill in group:
            hit = sorted((group - {skill}) & have)
            if hit:
                return hit[0]
    meta = SKILL_BY_NAME.get(skill)
    if meta:
        prereq = sorted(set(meta["prerequisites"]) & have)
        if prereq:
            return prereq[0]
    for profile in ROLE_PROFILES.values():
        for group in profile.get("any_of", []):
            if skill in group:
                hit = sorted((set(group) - {skill}) & have)
                if hit:
                    return hit[0]
    return None


def _tokens(text):
    stop = {"senior", "junior", "sr", "jr", "lead", "the", "a", "an", "of", "and", "i", "ii", "iii", "level", "entry"}
    return {t for t in re.findall(r"[a-z]+", (text or "").lower()) if t not in stop and len(t) > 1}


def title_match(jd_title, parsed, target_role):
    jd_t = _tokens(jd_title)
    if not jd_t:
        return 50, "No job title provided."
    titles = [e.get("title") or "" for e in parsed.get("experience", [])] + [target_role or ""]
    best = 0
    best_title = None
    for t in titles:
        tt = _tokens(t)
        if tt:
            overlap = len(jd_t & tt) / len(jd_t)
            if overlap > best:
                best, best_title = overlap, t
    score = int(30 + 70 * best)
    if best_title:
        return score, f"Closest title on your resume/profile: '{best_title}' ({int(best * 100)}% word overlap)."
    return score, "None of your listed titles resemble this job title."


def analyze_ats(parsed, resume_text, file_type, jd_parsed, jd_title, target_role=None, profile_years=None):
    have = set(parsed["skills"]["all"])
    lowered = resume_text.lower()
    required = jd_parsed.get("required_skills", [])
    preferred = jd_parsed.get("preferred_skills", [])

    rows = []
    for importance, skills in (("required", required), ("preferred", preferred)):
        for s in skills:
            if s in have:
                rows.append({"skill": s, "importance": importance, "status": "matched", "note": "Found in your resume."})
            else:
                rel = related_skill(s, have)
                if rel:
                    rows.append({"skill": s, "importance": importance, "status": "partial",
                                 "note": f"You list {rel}, which is closely related/transferable."})
                else:
                    rows.append({"skill": s, "importance": importance, "status": "missing", "note": "Not found in your resume."})
    jd_skills = set(required) | set(preferred)
    not_relevant = sorted(s for s in have - jd_skills if s not in SOFT_SKILL_NAMES)

    weight = {"required": 3, "preferred": 1}
    credit = {"matched": 1.0, "partial": 0.5, "missing": 0.0}
    total = sum(weight[r["importance"]] for r in rows)
    skills_score = int(100 * sum(weight[r["importance"]] * credit[r["status"]] for r in rows) / total) if total else 60

    keywords = jd_parsed.get("keywords", [])
    kw_matched = [k for k in keywords if k in have or re.search(r"(?<![a-z0-9])" + re.escape(k.lower()) + r"(?![a-z0-9])", lowered)]
    kw_missing = [k for k in keywords if k not in kw_matched]
    keyword_score = int(100 * len(kw_matched) / len(keywords)) if keywords else 60

    years_needed = jd_parsed.get("experience_years")
    years_have = estimate_years_experience(parsed, profile_years)
    if years_needed is None:
        exp_score, exp_note = 75, f"No explicit years requirement. Estimated experience: {years_have} year(s)."
    elif years_have >= years_needed:
        exp_score, exp_note = 100, f"Requires {years_needed}+ years; you have about {years_have}."
    else:
        exp_score = int(max(15, 100 * years_have / years_needed))
        exp_note = f"Requires {years_needed}+ years; your resume shows about {years_have}."

    edu_needed = jd_parsed.get("education_level")
    edu_have = max((e.get("level") or extract_education_level(" ".join(filter(None, [e.get("degree"), e.get("institution")]))) or "none"
                    for e in parsed.get("education", [])), key=lambda lv: EDU_RANK.get(lv, 0), default="none")
    if not edu_needed:
        edu_score, edu_note = 80, "No specific degree requirement stated."
    elif EDU_RANK.get(edu_have, 0) >= EDU_RANK.get(edu_needed, 0):
        edu_score, edu_note = 100, f"Requires {edu_needed}; you have {edu_have}."
    else:
        edu_score, edu_note = 40, f"Requires {edu_needed}; your resume shows {edu_have}."

    t_score, t_note = title_match(jd_title, parsed, target_role)
    soft_needed = jd_parsed.get("soft_skills", [])
    soft_rows = [{"skill": s, "status": "matched" if s in have else "missing"} for s in soft_needed]
    certs_needed = jd_parsed.get("certifications", [])
    resume_certs = " ".join(parsed.get("certifications", [])).lower()
    cert_rows = [{"certification": c, "status": "matched" if c[:20].lower() in resume_certs else "missing"} for c in certs_needed]
    format_component = score_ats(parsed, resume_text, file_type)

    overall = int(round(skills_score * 0.40 + keyword_score * 0.20 + exp_score * 0.15 + edu_score * 0.10
                        + t_score * 0.10 + format_component["score"] * 0.05))
    return {
        "ats_score": overall,
        "components": [
            {"key": "skills", "label": "Skills match", "score": skills_score, "weight": 0.40,
             "explanation": f"{sum(r['status'] == 'matched' for r in rows)} matched, {sum(r['status'] == 'partial' for r in rows)} "
                            f"partial, {sum(r['status'] == 'missing' for r in rows)} missing (required skills count 3x)."},
            {"key": "keywords", "label": "Keyword match", "score": keyword_score, "weight": 0.20,
             "explanation": f"{len(kw_matched)} of {len(keywords)} job keywords appear in your resume."},
            {"key": "experience", "label": "Experience match", "score": exp_score, "weight": 0.15, "explanation": exp_note},
            {"key": "education", "label": "Education match", "score": edu_score, "weight": 0.10, "explanation": edu_note},
            {"key": "title", "label": "Job-title match", "score": t_score, "weight": 0.10, "explanation": t_note},
            {"key": "format", "label": "Parser-friendliness", "score": format_component["score"], "weight": 0.05,
             "explanation": format_component["explanation"]},
        ],
        "skills": rows,
        "matched_keywords": kw_matched, "missing_keywords": kw_missing,
        "not_relevant": not_relevant,
        "soft_skills": soft_rows, "certifications": cert_rows,
        "technical_requirements": [r for r in rows if r["importance"] == "required"],
        "experience": {"required_years": years_needed, "estimated_years": years_have},
        "education": {"required": edu_needed, "have": edu_have},
        "disclaimer": "These are suggestions, not a guarantee of how a particular ATS will score your resume.",
    }
