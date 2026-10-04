"""Heuristic (non-AI) resume parser.

Produces the same structure as the AI extraction so everything downstream works
when AI is unavailable, and so AI output can be cross-checked against the text.
"""
import re

from .skill_extraction import (SKILL_BY_NAME, canonical_skill, extract_certifications, extract_education_level,
                               extract_skills)

SECTION_ALIASES = {
    "summary": ["summary", "professional summary", "objective", "career objective", "profile", "about me", "about"],
    "education": ["education", "academic background", "academics", "educational qualifications", "qualifications"],
    "experience": ["experience", "work experience", "professional experience", "employment", "employment history",
                   "work history", "internships", "internship", "internship experience", "relevant experience"],
    "projects": ["projects", "academic projects", "personal projects", "key projects", "technical projects", "project work"],
    "skills": ["skills", "technical skills", "core competencies", "technologies", "tech stack", "skills & tools",
               "skills and tools", "tools", "technical proficiency", "key skills"],
    "certifications": ["certifications", "certificates", "licenses & certifications", "licenses and certifications",
                       "courses", "certifications & courses"],
    "achievements": ["achievements", "awards", "honors", "honours", "accomplishments", "awards & achievements",
                     "achievements & awards", "extracurricular", "extra-curricular activities", "activities",
                     "leadership", "positions of responsibility"],
    "publications": ["publications", "research", "papers"],
}
HEADING_LOOKUP = {alias: key for key, aliases in SECTION_ALIASES.items() for alias in aliases}

EMAIL_RX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RX = re.compile(r"(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{3,4}[\s.\-]?\d{3,4}")
URL_RX = re.compile(r"(?:https?://)?(?:www\.)?[A-Za-z0-9\-]+\.(?:com|io|dev|me|org|net|in|co|app|ai)(?:/[^\s|,;)]*)?", re.I)
YEAR_RX = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")
BULLET_RX = re.compile(r"^\s*(?:[•●▪◦‣∙·\-*–—►➢✓]|\d+[.)])\s+")
INSTITUTION_RX = re.compile(r"\b(university|college|institute|school|academy|iit|nit|iiit|polytechnic)\b", re.I)

ACTION_VERBS = {
    "achieved", "architected", "automated", "built", "championed", "collaborated", "configured", "created", "decreased",
    "delivered", "deployed", "designed", "developed", "drove", "engineered", "enhanced", "established", "evaluated",
    "executed", "implemented", "improved", "increased", "integrated", "introduced", "launched", "led", "maintained",
    "managed", "mentored", "migrated", "modernized", "optimized", "orchestrated", "organized", "owned", "reduced",
    "refactored", "resolved", "scaled", "shipped", "simplified", "spearheaded", "streamlined", "tested", "trained",
    "analyzed", "analysed", "researched", "wrote", "programmed", "coordinated", "presented", "secured", "accelerated",
}
WEAK_OPENERS = re.compile(r"^(worked on|responsible for|helped|assisted|made|did|was involved in|involved in|"
                          r"participated in|handled|tasked with|duties included|i\s)", re.I)
METRIC_RX = re.compile(
    r"(\d+(?:\.\d+)?\s?(?:%|percent\b|x\b|k\b|\+?\s?(?:users|customers|clients|requests|transactions|records|rows|"
    r"students|members|people|downloads|stars|ms|seconds|minutes|hours|days|weeks|teams?|services|endpoints|apis|"
    r"projects|pages|queries|tickets|bugs|tests)\b))|([$€£₹]\s?\d)|"
    r"(\b(?:increased|reduced|improved|decreased|cut|saved|grew|boosted|accelerated|lowered)\b[^.\n]{0,40}\d)", re.I)


def has_metric(text):
    return bool(METRIC_RX.search(text or ""))


def _normalise_heading(line):
    cleaned = re.sub(r"[^a-z &\-]", "", line.lower()).strip(" -&")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return HEADING_LOOKUP.get(cleaned)


def split_sections(text):
    sections = {"header": []}
    current = "header"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        key = _normalise_heading(line) if len(line) <= 40 else None
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _entries(lines):
    """Group lines into entries: a header line followed by bullet lines."""
    entries, current = [], None

    def start(header):
        entry = {"header": header, "header_extra": "", "bullets": []}
        entries.append(entry)
        return entry

    for line in lines:
        is_bullet = bool(BULLET_RX.match(line))
        text = BULLET_RX.sub("", line).strip()
        if is_bullet:
            current = current or start("")
            current["bullets"].append(text)
        elif current and current["bullets"] and text[:1].islower():
            current["bullets"][-1] += " " + text          # wrapped continuation of the previous bullet
        elif current and not current["bullets"] and not current["header_extra"] and len(text) < 90:
            current["header_extra"] = text                 # second header line (title / dates)
        elif current and len(text) >= 90:
            current["bullets"].append(text)                # paragraph-style description
        else:
            current = start(text)
    return entries


def _split_header(header, extra):
    parts = [p.strip() for p in re.split(r"\s+[|–—@]\s+|\s+-\s+|,\s+(?=[A-Z])|\t", header) if p.strip()]
    dates = " ".join(YEAR_RX.findall(header + " " + extra))
    date_rx = re.compile(r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*\d{4}|\d{4}|present|current)", re.I)
    found_dates = date_rx.findall(header + " " + extra)
    first = parts[0] if parts else header
    second = parts[1] if len(parts) > 1 else (extra if extra and not date_rx.fullmatch(extra.strip()) else None)
    return first, second, (found_dates[0] if found_dates else None), (found_dates[-1] if len(found_dates) > 1 else None), dates


def _clean_link(url):
    url = url.strip().rstrip(".,;")
    if not url.lower().startswith("http"):
        url = "https://" + url
    return url


def parse_resume(text):
    sections = split_sections(text)
    header_text = "\n".join(sections.get("header", [])[:8])
    email = EMAIL_RX.search(text)
    phone = None
    for m in PHONE_RX.finditer(header_text or text[:600]):
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 15 and not YEAR_RX.fullmatch(m.group(0).strip()):
            phone = m.group(0).strip()
            break
    links = []
    for m in URL_RX.finditer(text):
        candidate = m.group(0)
        if "@" in text[max(0, m.start() - 1):m.start() + 1] or EMAIL_RX.fullmatch(candidate):
            continue
        if email and candidate in email.group(0):
            continue
        links.append(_clean_link(candidate))
    links = list(dict.fromkeys(links))[:10]
    github = next((link for link in links if "github.com" in link.lower()), None)
    linkedin = next((link for link in links if "linkedin.com" in link.lower()), None)

    name = None
    for line in sections.get("header", [])[:4]:
        candidate = re.split(r"\s[|•]\s", line)[0].strip()
        words = candidate.split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words) \
                and not EMAIL_RX.search(candidate) and not _normalise_heading(candidate):
            name = candidate.title() if candidate.isupper() else candidate
            break

    # Education
    education = []
    edu_lines = sections.get("education", [])
    for entry in _entries(edu_lines):
        block = " | ".join(x for x in [entry["header"], entry["header_extra"], *entry["bullets"]] if x)
        if not block.strip():
            continue
        institution = next((p for p in re.split(r"\s+[|,–—]\s+|,\s+|\s+-\s+", block) if INSTITUTION_RX.search(p)), None)
        level = extract_education_level(block)
        years = [int(y) for y in YEAR_RX.findall(block)]
        degree_match = re.search(r"((?:Bachelor|Master|B\.?\s?Tech|M\.?\s?Tech|B\.?S\.?c?|M\.?S\.?c?|B\.?E|M\.?E|Ph\.?D|MBA|BCA|MCA|Associate|Diploma)"
                                 r"[^|,\n]{0,60})", block)
        gpa = re.search(r"(?:GPA|CGPA)[:\s]*([0-9.]+\s*(?:/\s*[0-9.]+)?)", block, re.I)
        education.append({
            "institution": (institution or entry["header"])[:200],
            "degree": degree_match.group(1).strip() if degree_match else None,
            "level": level,
            "field_of_study": (re.search(r"\bin\s+([A-Z][A-Za-z &]{2,60})", degree_match.group(1)).group(1).strip()
                               if degree_match and re.search(r"\bin\s+([A-Z][A-Za-z &]{2,60})", degree_match.group(1)) else None),
            "graduation_year": max(years) if years else None,
            "gpa": gpa.group(1).strip() if gpa else None,
        })

    # Experience
    experience = []
    for entry in _entries(sections.get("experience", [])):
        if not entry["header"] and not entry["bullets"]:
            continue
        first, second, start, end, _ = _split_header(entry["header"], entry["header_extra"])
        header_all = f"{entry['header']} {entry['header_extra']}"
        kind = "internship" if re.search(r"\bintern(ship)?\b", header_all, re.I) else "job"
        experience.append({"company": (second if second and re.search(r"\b(engineer|developer|intern|analyst|manager|"
                                                                      r"scientist|designer|consultant|lead|associate|assistant)\b",
                                                                      first, re.I) else first)[:200],
                           "title": (first if second and re.search(r"\b(engineer|developer|intern|analyst|manager|scientist|"
                                                                   r"designer|consultant|lead|associate|assistant)\b", first, re.I)
                                     else second),
                           "kind": kind, "start_date": start, "end_date": end, "bullets": entry["bullets"][:12]})

    # Projects
    projects = []
    for entry in _entries(sections.get("projects", [])):
        if not entry["header"] and not entry["bullets"]:
            continue
        title, _, _, _, _ = _split_header(entry["header"], "")
        block = " ".join([entry["header"], entry["header_extra"], *entry["bullets"]])
        projects.append({"name": title[:200] or "Project", "description": " ".join(entry["bullets"])[:1500] or entry["header_extra"],
                         "technologies": sorted(extract_skills(block)), "bullets": entry["bullets"][:10]})

    skill_counts = extract_skills(text)
    certs = list(dict.fromkeys(
        [BULLET_RX.sub("", line).strip() for line in sections.get("certifications", []) if len(line) < 140]
        + [c for c in extract_certifications(text) if not _normalise_heading(c)]))[:15]
    achievements = [BULLET_RX.sub("", line).strip() for line in sections.get("achievements", []) if len(line) > 8][:12]
    publications = [BULLET_RX.sub("", line).strip() for line in sections.get("publications", []) if len(line) > 8][:10]
    summary = " ".join(sections.get("summary", []))[:1200] or None

    return build_parsed(
        contact={"name": name, "email": email.group(0) if email else None, "phone": phone, "location": None,
                 "github": github, "linkedin": linkedin, "links": links},
        summary=summary, education=education, experience=experience, projects=projects,
        skill_names=list(skill_counts), skill_counts=skill_counts, certifications=certs, achievements=achievements,
        publications=publications, sections_found=sorted(k for k in sections if k != "header" and sections[k]),
        text=text,
    )


def build_parsed(*, contact, summary, education, experience, projects, skill_names, skill_counts, certifications,
                 achievements, publications, sections_found, text):
    """Normalise into the canonical parsed_data structure."""
    by_cat = {"languages": [], "frameworks": [], "databases": [], "cloud_devops": [], "tools": [], "concepts": [], "soft": [],
              "other": []}
    cat_map = {"language": "languages", "frontend": "frameworks", "backend": "frameworks", "mobile": "frameworks",
               "database": "databases", "cloud": "cloud_devops", "devops": "cloud_devops", "tool": "tools",
               "testing": "tools", "data": "tools", "ml": "frameworks", "concept": "concepts", "security": "concepts",
               "soft": "soft"}
    for skill in sorted(set(skill_names)):
        meta = SKILL_BY_NAME.get(skill)
        by_cat[cat_map.get(meta["category"], "other") if meta else "other"].append(skill)

    bullets = []
    for item in experience:
        bullets.extend({"text": b, "section": "experience", "source": item.get("company")} for b in item.get("bullets", []))
    for item in projects:
        project_bullets = item.get("bullets") or ([item["description"]] if item.get("description") else [])
        bullets.extend({"text": b, "section": "projects", "source": item.get("name")} for b in project_bullets)

    words = len(re.findall(r"\w+", text))
    return {
        "contact": contact,
        "summary": summary,
        "education": education,
        "experience": experience,
        "projects": projects,
        "skills": {"all": sorted(set(skill_names)), "by_category": by_cat,
                   "mentions": {k: v for k, v in (skill_counts or {}).items()}},
        "certifications": certifications,
        "achievements": achievements,
        "publications": publications,
        "sections_found": sections_found,
        "bullets": bullets[:60],
        "word_count": words,
    }


def merge_ai_extraction(heuristic, ai, text):
    """Merge AI extraction into heuristic output, rejecting AI claims that aren't grounded in the text."""
    lowered = text.lower()

    def grounded(value):
        """True if the (start of the) value appears in the resume as whole words."""
        if not value:
            return False
        needle = re.escape(value.lower()[:40].strip())
        return bool(needle) and re.search(r"(?<![a-z0-9])" + needle + r"(?![a-z0-9])", lowered) is not None

    ai_skill_names = set()
    for raw in [*ai.skills, *ai.programming_languages, *ai.frameworks, *ai.tools]:
        canonical = canonical_skill(raw)
        if canonical and canonical in heuristic["skills"]["all"]:
            ai_skill_names.add(canonical)
        elif canonical and re.search(re.escape(raw.lower()), lowered):
            ai_skill_names.add(canonical)
        elif not canonical and re.search(r"(?<![a-z0-9])" + re.escape(raw.lower()) + r"(?![a-z0-9])", lowered):
            ai_skill_names.add(raw.strip())  # non-taxonomy skill that literally appears in the resume
    skill_names = sorted(set(heuristic["skills"]["all"]) | ai_skill_names)
    counts = dict(heuristic["skills"].get("mentions", {}))
    for s in skill_names:
        counts.setdefault(s, 1)

    contact = dict(heuristic["contact"])
    for key in ("name", "email", "phone", "location", "github", "linkedin"):
        value = getattr(ai, key)
        if value and (grounded(value) or key == "name" and value.split()[0].lower() in lowered):
            contact[key] = value
    contact["links"] = list(dict.fromkeys(contact.get("links", []) + [link for link in ai.links if grounded(link.split("//")[-1])]))[:10]

    education = [e.model_dump() | {"level": extract_education_level(" ".join(filter(None, [e.degree, e.field_of_study])))}
                 for e in ai.education if e.institution and grounded(e.institution)] or heuristic["education"]
    experience = [x.model_dump() for x in ai.experience if x.company and grounded(x.company)] or heuristic["experience"]
    projects = []
    for p in ai.projects:
        if p.name and grounded(p.name):
            techs = sorted({canonical_skill(t) or t for t in p.technologies if t.lower() in lowered})
            projects.append({"name": p.name, "description": p.description, "technologies": techs,
                             "bullets": [p.description] if p.description else []})
    projects = projects or heuristic["projects"]

    return build_parsed(
        contact=contact, summary=ai.summary if ai.summary and grounded(ai.summary[:30]) else heuristic["summary"],
        education=education, experience=experience, projects=projects, skill_names=skill_names, skill_counts=counts,
        certifications=list(dict.fromkeys(heuristic["certifications"] + [c for c in ai.certifications if grounded(c)]))[:15],
        achievements=[a for a in ai.achievements if grounded(a[:30])] or heuristic["achievements"],
        publications=[p for p in ai.publications if grounded(p[:30])] or heuristic["publications"],
        sections_found=heuristic["sections_found"], text=text,
    )
