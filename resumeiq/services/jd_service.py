"""Job description analysis (heuristic extraction, optionally enriched by AI and grounded in the text)."""
import re

from ..extensions import db
from ..models import JobDescription
from .ai import SYSTEM_GUARDRAILS, AIUnavailable, get_ai
from .ai.schemas import JDExtraction
from .skill_extraction import (SOFT_SKILL_NAMES, canonical_skill, classify_requirements, extract_certifications,
                               extract_education_level, extract_skills, extract_years_required, split_jd_sections)

SALARY_RX = re.compile(
    r"([$€£₹]\s?\d[\d,]*(?:\.\d+)?\s?[kK]?(?:\s?(?:-|–|to)\s?[$€£₹]?\s?\d[\d,]*(?:\.\d+)?\s?[kK]?)?"
    r"(?:\s?(?:per|/|a)\s?(?:year|yr|annum|hour|hr|month))?)")
BULLET = re.compile(r"^\s*(?:[•●▪◦‣∙·\-*–—►➢✓]|\d+[.)])\s+")


def detect_work_type(text):
    t = (text or "").lower()
    if "hybrid" in t:
        return "hybrid"
    if re.search(r"\b(fully remote|100% remote|remote[- ]first|work from home|remote position|remote role|\bremote\b)", t):
        return "remote"
    if re.search(r"\b(on-?site|in[- ]office|in person)\b", t):
        return "onsite"
    return "unknown"


def heuristic_jd(text, title=None):
    required, preferred = classify_requirements(text)
    all_found = extract_skills(text)
    soft = sorted(s for s in all_found if s in SOFT_SKILL_NAMES)
    required = [s for s in required if s not in SOFT_SKILL_NAMES]
    preferred = [s for s in preferred if s not in SOFT_SKILL_NAMES]
    sections = split_jd_sections(text)
    responsibilities = [BULLET.sub("", line).strip() for line in sections["responsibilities"].splitlines()
                        if BULLET.match(line) and len(line.strip()) > 10][:15]
    salary = SALARY_RX.search(text)
    keywords = sorted(set(required) | set(preferred))
    return {
        "title": title, "required_skills": required, "preferred_skills": preferred, "soft_skills": soft,
        "responsibilities": responsibilities, "experience_years": extract_years_required(text),
        "education_level": extract_education_level(text), "certifications": extract_certifications(text),
        "keywords": keywords, "salary_text": salary.group(1).strip() if salary else None,
        "work_type": detect_work_type(text), "method": "heuristic",
    }


def merge_ai_jd(base, ai: JDExtraction, text):
    lowered = text.lower()

    def canon(items):
        out = []
        for raw in items:
            c = canonical_skill(raw) or (raw.strip() if raw.strip().lower() in lowered and len(raw) <= 40 else None)
            if c and (c.lower() in lowered or c in extract_skills(text) or raw.lower() in lowered):
                out.append(c)
        return out

    required = sorted(set(base["required_skills"]) | (set(canon(ai.required_skills)) - set(base["preferred_skills"])))
    preferred = sorted((set(base["preferred_skills"]) | set(canon(ai.preferred_skills))) - set(required))
    merged = dict(base)
    merged.update({
        "title": base["title"] or ai.title,
        "company": ai.company if ai.company and ai.company.lower() in lowered else None,
        "required_skills": [s for s in required if s not in SOFT_SKILL_NAMES],
        "preferred_skills": [s for s in preferred if s not in SOFT_SKILL_NAMES],
        "soft_skills": sorted(set(base["soft_skills"]) | {s for s in ai.soft_skills if s.lower() in lowered}),
        "responsibilities": base["responsibilities"] or [r for r in ai.responsibilities if r[:25].lower() in lowered][:15],
        "experience_years": base["experience_years"] if base["experience_years"] is not None else ai.experience_years,
        "certifications": list(dict.fromkeys(base["certifications"] + [c for c in ai.certifications if c[:20].lower() in lowered]))[:10],
        "keywords": sorted(set(base["keywords"]) | {k for k in ai.keywords if k.lower() in lowered and len(k) <= 40}),
        "salary_text": base["salary_text"] or (ai.salary_text if ai.salary_text and ai.salary_text[:6].lower() in lowered else None),
        "method": "ai+heuristic",
    })
    return merged


def analyze_job_description(user_id, title, text, company=None, use_ai=True):
    text = text.strip()
    parsed = heuristic_jd(text, title)
    ai_used = False
    ai_note = None
    ai = get_ai()
    if use_ai and ai.available_for(user_id):
        try:
            result = ai.generate(service="jd_extraction", user_id=user_id, schema=JDExtraction, temperature=0.1,
                                 system=SYSTEM_GUARDRAILS,
                                 prompt="Extract the requirements from this job description. Separate required from "
                                        "preferred/nice-to-have skills. Only include what is stated.\n\n"
                                        f"<job_description>\n{text[:12000]}\n</job_description>")
            parsed = merge_ai_jd(parsed, result, text)
            ai_used = True
        except AIUnavailable as exc:
            ai_note = exc.user_message
    parsed["ai_note"] = ai_note
    if company:
        parsed["company"] = company
    jd = JobDescription(user_id=user_id, title=title[:200], company=(company or parsed.get("company") or None),
                        raw_text=text[:30000], parsed=parsed, ai_used=ai_used)
    db.session.add(jd)
    db.session.flush()
    return jd
