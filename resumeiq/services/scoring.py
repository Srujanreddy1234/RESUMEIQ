"""Transparent resume scoring rubric.

The LLM never produces these numbers. Each component is computed from evidence
in the parsed resume and returns: score (0-100), weight, a plain-English
explanation of WHY, the evidence used, and concrete suggestions.
"""
import re

from .resume_parser import ACTION_VERBS, WEAK_OPENERS, has_metric
from .skill_extraction import SOFT_SKILL_NAMES

WEIGHTS = {
    "skills": 0.14, "experience": 0.15, "education": 0.08, "keywords": 0.12, "projects": 0.12,
    "achievements": 0.06, "formatting": 0.08, "ats": 0.10, "impact": 0.09, "role_relevance": 0.06,
}
LABELS = {
    "skills": "Skills", "experience": "Experience", "education": "Education", "keywords": "Keywords",
    "projects": "Projects", "achievements": "Achievements", "formatting": "Formatting", "ats": "ATS compatibility",
    "impact": "Quantifiable impact", "role_relevance": "Role relevance",
}
IMPORTANCE_WEIGHT = {"core": 3.0, "important": 2.0, "nice": 1.0, "required": 3.0, "preferred": 1.0}


def _clamp(v):
    return int(max(0, min(100, round(v))))


def _component(key, score, explanation, evidence=None, suggestions=None):
    return {"key": key, "label": LABELS[key], "score": _clamp(score), "weight": WEIGHTS[key],
            "explanation": explanation, "evidence": evidence or {}, "suggestions": suggestions or []}


def _first_word(text):
    m = re.match(r"\s*([A-Za-z]+)", text or "")
    return m.group(1).lower() if m else ""


def score_skills(parsed):
    tech = [s for s in parsed["skills"]["all"] if s not in SOFT_SKILL_NAMES]
    cats = {k for k, v in parsed["skills"]["by_category"].items() if v and k not in ("soft", "other")}
    score = min(100, len(tech) * 5 + len(cats) * 8)
    expl = (f"Your resume lists {len(tech)} recognised technical skill(s) across {len(cats)} categor"
            f"{'y' if len(cats) == 1 else 'ies'} ({', '.join(sorted(cats)) or 'none'}).")
    sugg = []
    if len(tech) < 8:
        sugg.append("List more of the concrete tools and technologies you have actually used.")
    if "databases" not in cats:
        sugg.append("If you've worked with a database (e.g. PostgreSQL, MySQL, MongoDB), name it explicitly.")
    if "cloud_devops" not in cats:
        sugg.append("Mention any Git, Docker, CI/CD or cloud experience — recruiters scan for these.")
    return _component("skills", score, expl, {"technical_skills": len(tech), "categories": sorted(cats)}, sugg)


def score_experience(parsed):
    entries = parsed["experience"]
    bullets = [b for e in entries for b in e.get("bullets", [])]
    if not entries:
        has_projects = bool(parsed["projects"])
        score = 30 if has_projects else 10
        return _component("experience", score,
                          "No work or internship experience section was detected"
                          + ("; your projects partly compensate." if has_projects else "."),
                          {"entries": 0},
                          ["Add internships, part-time roles, freelance or open-source contributions as experience entries.",
                           "Use a clear 'Experience' heading so parsers can find it."])
    action = sum(1 for b in bullets if _first_word(b) in ACTION_VERBS)
    weak = sum(1 for b in bullets if WEAK_OPENERS.match(b))
    ratio = action / len(bullets) if bullets else 0
    internships = sum(1 for e in entries if e.get("kind") == "internship")
    score = 45 + min(len(entries), 3) * 10 + ratio * 25 - min(weak, 4) * 3 + (5 if len(bullets) >= 6 else 0)
    expl = (f"{len(entries)} experience entr{'y' if len(entries) == 1 else 'ies'} ({internships} internship"
            f"{'' if internships == 1 else 's'}) with {len(bullets)} bullet(s); {action} start with a strong action verb"
            + (f" and {weak} start with weak phrasing like 'worked on' or 'responsible for'." if weak else "."))
    sugg = []
    if ratio < 0.6:
        sugg.append("Start each bullet with a strong action verb (Built, Designed, Reduced, Automated...).")
    if weak:
        sugg.append("Replace 'responsible for' / 'worked on' with what you actually did and its result.")
    if len(bullets) < len(entries) * 2:
        sugg.append("Give each role 2-5 bullets describing concrete contributions.")
    return _component("experience", score, expl,
                      {"entries": len(entries), "bullets": len(bullets), "action_verb_bullets": action, "weak_bullets": weak},
                      sugg)


def score_education(parsed):
    edu = parsed["education"]
    if not edu:
        return _component("education", 20, "No education section was detected.", {},
                          ["Add an Education section with degree, institution and graduation year."])
    e = edu[0]
    score = 30 + (25 if e.get("degree") or e.get("level") else 0) + (20 if e.get("institution") else 0) \
        + (15 if e.get("graduation_year") else 0) + (10 if e.get("gpa") or e.get("field_of_study") else 0)
    missing = [label for label, ok in (("degree", e.get("degree") or e.get("level")), ("institution", e.get("institution")),
                                       ("graduation year", e.get("graduation_year"))) if not ok]
    expl = "Education section found" + (f", but it is missing: {', '.join(missing)}." if missing else " with degree, institution and graduation year.")
    return _component("education", score, expl, {"entries": len(edu)},
                      [f"Add your {m}." for m in missing])


def score_keywords(parsed, requirements, word_count):
    have = set(parsed["skills"]["all"])
    if requirements:
        total = sum(IMPORTANCE_WEIGHT.get(r["importance"], 1) for r in requirements)
        hit = [r for r in requirements if r["skill"] in have]
        got = sum(IMPORTANCE_WEIGHT.get(r["importance"], 1) for r in hit)
        missing = [r["skill"] for r in requirements if r["skill"] not in have]
        score = 100 * got / total if total else 50
        expl = (f"Your resume contains {len(hit)} of {len(requirements)} target keywords "
                f"(weighted by importance: {round(score)}%).")
        sugg = [f"If you genuinely have experience with {', '.join(missing[:5])}, mention it explicitly."] if missing else []
        return _component("keywords", score, expl, {"matched": sorted(r["skill"] for r in hit), "missing": missing}, sugg)
    density = len(have) / max(word_count, 1) * 100
    score = min(100, 30 + density * 12)
    return _component("keywords", score,
                      f"No target role or job description was given, so this measures general technical keyword density "
                      f"({len(have)} recognised terms in {word_count} words).", {"terms": len(have)},
                      ["Run an ATS analysis against a specific job description for a precise keyword score."])


def score_projects(parsed):
    projects = parsed["projects"]
    if not projects:
        return _component("projects", 15, "No projects section was detected.", {},
                          ["Add 2-4 projects with the technologies used and what each achieved."])
    with_tech = sum(1 for p in projects if len(p.get("technologies") or []) >= 2)
    texts = [" ".join([p.get("description") or "", *(p.get("bullets") or [])]) for p in projects]
    with_metrics = sum(1 for t in texts if has_metric(t))
    score = 30 + min(len(projects), 3) * 10 + (with_tech / len(projects)) * 20 + (with_metrics / len(projects)) * 20
    expl = (f"{len(projects)} project(s) found; {with_tech} name their technologies and {with_metrics} include a "
            f"measurable outcome.")
    if with_metrics < len(projects):
        expl += " Projects that describe technologies but not results score lower."
    sugg = []
    if with_metrics < len(projects):
        sugg.append("For each project, add a measurable result you can verify (users, latency, accuracy, time saved).")
    if with_tech < len(projects):
        sugg.append("List the main technologies used in each project.")
    if len(projects) < 2:
        sugg.append("Add at least one more substantial project relevant to your target role.")
    return _component("projects", score, expl,
                      {"projects": len(projects), "with_technologies": with_tech, "with_metrics": with_metrics}, sugg)


def score_achievements(parsed):
    count = len(parsed["achievements"]) + len(parsed["certifications"]) + len(parsed["publications"])
    score = 35 + min(count, 4) * 16
    expl = (f"Found {len(parsed['achievements'])} achievement(s), {len(parsed['certifications'])} certification(s) and "
            f"{len(parsed['publications'])} publication(s).")
    sugg = [] if count >= 3 else ["Add awards, hackathon results, scholarships, certifications or leadership roles if you have them."]
    return _component("achievements", score, expl, {"count": count}, sugg)


def score_formatting(parsed, text):
    found = set(parsed["sections_found"])
    expected = {"education", "skills"} | ({"experience"} if parsed["experience"] else {"projects"})
    present = expected & found
    words = parsed["word_count"]
    lines = [line for line in text.splitlines() if line.strip()]
    long_lines = sum(1 for line in lines if len(line.split()) > 45)
    bullets = len(parsed["bullets"])
    score = 40 * len(present) / len(expected)
    length_note = "a good length"
    if 300 <= words <= 1000:
        score += 30
    elif words < 300:
        score += 12
        length_note = "short"
    else:
        score += 15
        length_note = "long for a one-to-two page resume"
    score += 20 if bullets >= 5 else bullets * 3
    score += 10 if long_lines <= 2 else max(0, 10 - long_lines * 2)
    expl = (f"Detected {len(present)} of {len(expected)} expected sections ({', '.join(sorted(present)) or 'none'}); "
            f"{words} words ({length_note}); {bullets} bullet points; {long_lines} very long line(s).")
    sugg = []
    if expected - present:
        sugg.append(f"Add clearly titled sections: {', '.join(sorted(expected - present))}.")
    if words > 1000:
        sugg.append("Trim to the most relevant content; aim for one page (two at most).")
    if long_lines > 2:
        sugg.append("Break long paragraphs into concise bullet points.")
    return _component("formatting", score, expl, {"sections": sorted(found), "words": words, "bullets": bullets}, sugg)


def score_ats(parsed, text, file_type):
    contact = parsed["contact"]
    standard = {"education", "experience", "skills", "projects"} & set(parsed["sections_found"])
    junk = len(re.findall(r"[^\x00-\x7F•–—’‘“”€£₹·]", text)) / max(len(text), 1)
    score = 20  # text was extractable
    score += 15 if contact.get("email") else 0
    score += 10 if contact.get("phone") else 0
    score += 25 * min(len(standard), 3) / 3
    score += 15 if junk < 0.01 else (7 if junk < 0.03 else 0)
    score += 15 if file_type in ("pdf", "docx") else 8
    issues = []
    if not contact.get("email"):
        issues.append("no email address found")
    if not contact.get("phone"):
        issues.append("no phone number found")
    if len(standard) < 3:
        issues.append("few standard section headings")
    if junk >= 0.01:
        issues.append("unusual symbols/icons that some parsers mis-read")
    expl = "Text extracted cleanly" + (f", but: {'; '.join(issues)}." if issues else " with contact details and standard headings.")
    sugg = []
    if issues:
        sugg.append("Use standard headings (Experience, Education, Skills, Projects) and plain-text contact details.")
    if junk >= 0.01:
        sugg.append("Avoid icon fonts, text inside images, and multi-column tables.")
    sugg.append("This is an estimate of parser-friendliness, not a guarantee of how a specific ATS will score you.")
    return _component("ats", score, expl, {"standard_sections": sorted(standard), "file_type": file_type}, sugg)


def score_impact(parsed):
    bullets = [b["text"] for b in parsed["bullets"]]
    if not bullets:
        return _component("impact", 15, "No bullet points were found to evaluate for measurable impact.", {},
                          ["Describe your work as bullet points that include outcomes."])
    with_metric = [b for b in bullets if has_metric(b)]
    ratio = len(with_metric) / len(bullets)
    score = 20 + ratio * 80
    expl = f"{len(with_metric)} of {len(bullets)} bullet points include a measurable result (numbers, %, scale or time)."
    sugg = ["Where you have real figures, add them (e.g. users served, % faster, records processed). "
            "Don't invent numbers — use 'Add a measurable result here' as a reminder."] if ratio < 0.5 else []
    return _component("impact", score, expl, {"bullets": len(bullets), "with_metrics": len(with_metric)}, sugg)


def score_role_relevance(parsed, role_name, requirements):
    if not requirements:
        return _component("role_relevance", 50,
                          "No target role set, so relevance is neutral. Set a target career in your profile.", {},
                          ["Choose a target role to get a role-specific relevance score."])
    have = set(parsed["skills"]["all"])
    core = [r for r in requirements if r["importance"] == "core"]
    important = [r for r in requirements if r["importance"] == "important"]
    core_hit = sum(1 for r in core if r["skill"] in have or set(r.get("alternatives", [])) & have)
    imp_hit = sum(1 for r in important if r["skill"] in have)
    score = (70 * core_hit / len(core) if core else 35) + (30 * imp_hit / len(important) if important else 15)
    expl = (f"For {role_name}: you show {core_hit} of {len(core)} core skills and {imp_hit} of {len(important)} "
            f"important skills from our curated role baseline.")
    missing_core = [r["skill"] for r in core if r["skill"] not in have and not set(r.get("alternatives", [])) & have]
    sugg = [f"Core skills for this role you haven't listed: {', '.join(missing_core[:6])}."] if missing_core else []
    return _component("role_relevance", score, expl, {"core_hit": core_hit, "core_total": len(core)}, sugg)


def score_resume(parsed, text, file_type, role_name=None, requirements=None, keyword_requirements=None):
    """Return {"overall": int, "components": [...], "grade": str}."""
    components = [
        score_skills(parsed),
        score_experience(parsed),
        score_education(parsed),
        score_keywords(parsed, keyword_requirements or requirements, parsed["word_count"]),
        score_projects(parsed),
        score_achievements(parsed),
        score_formatting(parsed, text),
        score_ats(parsed, text, file_type),
        score_impact(parsed),
        score_role_relevance(parsed, role_name, requirements),
    ]
    total_w = sum(c["weight"] for c in components)
    overall = _clamp(sum(c["score"] * c["weight"] for c in components) / total_w)
    return {"overall": overall, "components": components, "grade": grade(overall)}


def grade(score):
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Strong"
    if score >= 55:
        return "Good foundation"
    if score >= 40:
        return "Needs work"
    return "Significant gaps"


def strengths_and_weaknesses(components):
    ordered = sorted(components, key=lambda c: -c["score"])
    strengths = [f"{c['label']} ({c['score']}): {c['explanation']}" for c in ordered[:3] if c["score"] >= 65]
    weaknesses = [f"{c['label']} ({c['score']}): {c['explanation']}" for c in ordered[::-1][:3] if c["score"] < 65]
    return strengths, weaknesses
