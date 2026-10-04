"""SkillExtractionService: deterministic, taxonomy-based skill and requirement extraction.

This is the non-LLM backbone. AI output is merged with (never substituted for)
these results, so scores and gaps stay explainable and reproducible.
"""
import re
from functools import lru_cache

from ..data.taxonomy import ROLE_PROFILES, SKILLS
from ..extensions import db

SKILL_BY_NAME = {s["name"]: s for s in SKILLS}


def _alias_pattern(alias):
    escaped = re.escape(alias).replace(r"\ ", r"[\s\-]?")
    return rf"(?<![A-Za-z0-9_+#]){escaped}(?![A-Za-z0-9_+#])"


@lru_cache(maxsize=1)
def _compiled():
    compiled = []
    for skill in SKILLS:
        ci_terms = [skill["name"]] + [a for a in skill["aliases"]]
        cs_terms = skill["case_sensitive_aliases"]
        ci_terms = [t for t in ci_terms if t not in cs_terms]
        patterns = []
        # Very short names (C, R, Go) are only matched by explicit regex.
        ci = [t for t in ci_terms if len(t) > 1 and not (skill["regex"] and t == skill["name"])]
        if ci:
            patterns.append(re.compile("|".join(_alias_pattern(t) for t in ci), re.I))
        if cs_terms:
            patterns.append(re.compile("|".join(_alias_pattern(t) for t in cs_terms)))
        if skill["regex"]:
            patterns.append(re.compile(skill["regex"], re.M))
        compiled.append((skill["name"], patterns))
    return compiled


@lru_cache(maxsize=1)
def _alias_lookup():
    lookup = {}
    for skill in SKILLS:
        for term in [skill["name"], *skill["aliases"], *skill["case_sensitive_aliases"]]:
            lookup.setdefault(term.lower(), skill["name"])
    return lookup


def canonical_skill(name):
    """Map any alias/spelling to the canonical taxonomy name, or None."""
    if not name:
        return None
    key = re.sub(r"\s+", " ", name.strip().lower())
    lookup = _alias_lookup()
    if key in lookup:
        return lookup[key]
    stripped = re.sub(r"[\s\.\-]?(js)$", ".js", key)
    return lookup.get(stripped)


def extract_skills(text):
    """Return {canonical_skill_name: mention_count} found in free text."""
    found = {}
    if not text:
        return found
    for name, patterns in _compiled():
        count = sum(len(p.findall(text)) for p in patterns)
        if count:
            found[name] = count
    return found


# ── Job-description structure ───────────────────────────────────────────
PREFERRED_HEADINGS = re.compile(
    r"^\s*(?:[#*\-•]\s*)?(nice[\s\-]to[\s\-]have|preferred|bonus|pluses|good to have|desirable|"
    r"preferred qualifications|it'?s a plus|additional skills)\b.*$", re.I | re.M)
REQUIRED_HEADINGS = re.compile(
    r"^\s*(?:[#*\-•]\s*)?(requirements|required|qualifications|must[\s\-]have|minimum qualifications|"
    r"basic qualifications|what you'?ll need|you have|skills|what we'?re looking for)\b.*$", re.I | re.M)
RESPONSIBILITY_HEADINGS = re.compile(
    r"^\s*(?:[#*\-•]\s*)?(responsibilities|what you'?ll do|the role|duties|your role|in this role)\b.*$", re.I | re.M)
OTHER_HEADINGS = re.compile(r"^\s*(?:[#*\-•]\s*)?(benefits|perks|about us|about the company|compensation|"
                            r"what we offer|equal opportunity)\b.*$", re.I | re.M)


def split_jd_sections(text):
    """Split a job description into {required, preferred, responsibilities, other, preamble} text blocks."""
    marks = []
    for kind, rx in (("preferred", PREFERRED_HEADINGS), ("required", REQUIRED_HEADINGS),
                     ("responsibilities", RESPONSIBILITY_HEADINGS), ("other", OTHER_HEADINGS)):
        for m in rx.finditer(text):
            # Headings are short lines.
            if len(m.group(0).strip()) <= 60:
                marks.append((m.start(), kind))
    marks.sort()
    sections = {"preamble": "", "required": "", "preferred": "", "responsibilities": "", "other": ""}
    if not marks:
        sections["required"] = text
        return sections
    sections["preamble"] = text[:marks[0][0]]
    for i, (start, kind) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        sections[kind] += "\n" + text[start:end]
    return sections


PREFERRED_INLINE = re.compile(r"(nice to have|preferred|is a plus|a plus|bonus|familiarity with|exposure to)", re.I)


def classify_requirements(text):
    """Return (required_skills, preferred_skills) as sorted canonical names."""
    sections = split_jd_sections(text)
    preferred = set(extract_skills(sections["preferred"]))
    # Sentence-level hints like "Experience with Redis is a plus" outside a "preferred" heading.
    strong, soft = set(), set()
    body = "\n".join((sections["preamble"], sections["required"], sections["responsibilities"]))
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
        found = set(extract_skills(sentence))
        (soft if PREFERRED_INLINE.search(sentence) else strong).update(found)
    preferred |= soft - strong
    required = strong - preferred
    return sorted(required), sorted(preferred)


YEARS_RX = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*(\d{1,2})\s*)?\+?\s*(?:years?|yrs?)(?:\s+of)?"
    r"(?:\s+\w+){0,4}?\s+(?:experience|exp\b)", re.I)


def extract_years_required(text):
    values = []
    for m in YEARS_RX.finditer(text or ""):
        low = int(m.group(1))
        if 0 < low <= 20:
            values.append(low)
    return min(values) if values else None


EDUCATION_LEVELS = [
    ("phd", re.compile(r"\b(ph\.?\s?d|doctorate|doctoral)\b", re.I)),
    ("masters", re.compile(r"\b(master'?s?|m\.?s\.?c?|m\.?tech|mba|m\.?eng|m\.?e\.?)\b(?:\s+(?:degree|in|of))?", re.I)),
    ("bachelors", re.compile(r"\b(bachelor'?s?|b\.?s\.?c?|b\.?tech|b\.?e\.?|b\.?eng|undergraduate degree|bca|b\.?a\.?)\b(?:\s+(?:degree|in|of))?", re.I)),
    ("associate", re.compile(r"\b(associate'?s? degree|diploma)\b", re.I)),
]
EDU_RANK = {"none": 0, "associate": 1, "bachelors": 2, "masters": 3, "phd": 4}


def extract_education_level(text):
    for level, rx in EDUCATION_LEVELS:
        if rx.search(text or ""):
            return level
    return None


CERT_RX = re.compile(r"\b((?:AWS|Azure|Google Cloud|GCP|Oracle|Cisco|CompTIA|Microsoft|Kubernetes|Terraform|Salesforce|"
                     r"PMP|CKA|CKAD|CISSP|CEH|Scrum|PSM|CSM|ISTQB)[A-Za-z0-9 +\-/()]{0,60}?(?:Certified|Certification|"
                     r"Associate|Professional|Practitioner|Fundamentals|Administrator|Developer|Security\+|Network\+|A\+)?)\b")
CERT_HINT = re.compile(r"certif|\bCKA\b|\bCKAD\b|\bPMP\b|\bCISSP\b|\bCEH\b|Security\+|\bAZ-\d{3}\b", re.I)


def extract_certifications(text):
    out = []
    for line in (text or "").splitlines():
        if CERT_HINT.search(line):
            cleaned = re.sub(r"^[\s•\-*·]+", "", line).strip()
            if 4 <= len(cleaned) <= 120:
                out.append(cleaned)
    return list(dict.fromkeys(out))[:15]


SOFT_SKILL_NAMES = {s["name"] for s in SKILLS if s["is_soft"]}


# ── Role profiles ────────────────────────────────────────────────────────
def resolve_role(role_text):
    """Map free-text role to a curated profile name (or None)."""
    if not role_text:
        return None
    key = role_text.strip().lower()
    key = re.sub(r"\b(senior|sr\.?|junior|jr\.?|lead|principal|staff|entry[\s\-]level|intern(ship)?|associate|graduate|i{1,3}|[123])\b", " ", key)
    key = re.sub(r"\s+", " ", key).strip()
    best, best_len = None, 0
    for name, profile in ROLE_PROFILES.items():
        for term in [name.lower(), *profile["aliases"]]:
            if term == key:
                return name
            if term in key and len(term) > best_len:
                best, best_len = name, len(term)
    if best:
        return best
    # Loose keyword fallbacks
    for kw, name in (("backend", "Backend Developer"), ("back-end", "Backend Developer"), ("frontend", "Frontend Developer"),
                     ("front-end", "Frontend Developer"), ("full", "Full Stack Developer"), ("data scien", "Data Scientist"),
                     ("data analy", "Data Analyst"), ("data engineer", "Data Engineer"), ("machine learning", "Machine Learning Engineer"),
                     ("devops", "DevOps Engineer"), ("cloud", "Cloud Engineer"), ("android", "Mobile Developer"),
                     ("ios", "Mobile Developer"), ("security", "Cybersecurity Analyst"), ("qa", "QA Engineer"),
                     ("test", "QA Engineer"), ("java", "Java Developer"), ("python", "Python Developer"),
                     ("software", "Software Engineer"), ("developer", "Software Engineer"), ("engineer", "Software Engineer")):
        if kw in key:
            return name
    return None


def role_requirements(role_text, user_skill_names=()):
    """Curated requirements for a role: list of {skill, importance, level}. `any_of` groups resolve to the
    option the user already has, else the first option."""
    profile_name = resolve_role(role_text)
    if not profile_name:
        return None, []
    profile = ROLE_PROFILES[profile_name]
    reqs = [{"skill": s, "importance": imp, "level": lvl} for s, imp, lvl in profile["skills"]]
    have = set(user_skill_names)
    for group in profile.get("any_of", []):
        choice = next((g for g in group if g in have), group[0])
        reqs.append({"skill": choice, "importance": "core", "level": 3, "alternatives": group})
    return profile_name, reqs


# ── Database helpers ─────────────────────────────────────────────────────
def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("+", "plus").replace("#", "sharp")).strip("-") or "skill"


def seed_skills():
    from ..models import Skill
    existing = {s.name for s in Skill.query.all()}
    for s in SKILLS:
        if s["name"] in existing:
            continue
        db.session.add(Skill(name=s["name"], slug=slugify(s["name"]), category=s["category"],
                             description=s["description"] or None, difficulty=s["difficulty"],
                             est_hours=s["est_hours"], is_soft=s["is_soft"]))
    db.session.flush()


def skill_rows(names, create_unknown=False):
    """Return {name: Skill} for canonical names, optionally creating unknown (AI-found) skills."""
    from ..models import Skill
    names = [n for n in dict.fromkeys(names) if n]
    if not names:
        return {}
    rows = {s.name: s for s in Skill.query.filter(Skill.name.in_(names)).all()}
    if create_unknown:
        for name in names:
            if name in rows:
                continue
            clean = re.sub(r"\s+", " ", name).strip()
            if not (2 <= len(clean) <= 40) or not re.fullmatch(r"[A-Za-z0-9 .+#/\-]+", clean):
                continue
            slug = slugify(clean)
            existing = Skill.query.filter_by(slug=slug).first()
            if existing:
                rows[name] = existing
                continue
            skill = Skill(name=clean, slug=slug, category="other", difficulty=2, est_hours=15)
            db.session.add(skill)
            db.session.flush()
            rows[name] = skill
    return rows
