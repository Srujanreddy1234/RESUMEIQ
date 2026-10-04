"""CoverLetterService. Uses only facts from the resume and job description - never invents experience."""
from .ai import SYSTEM_GUARDRAILS, AIUnavailable, get_ai
from .ai.schemas import CoverLetterOut

TONES = {
    "formal": "formal and professional",
    "concise": "concise (under 220 words), direct and professional",
    "enthusiastic": "warm and enthusiastic while staying professional",
    "technical": "technical, emphasising engineering depth and specific technologies",
}


def resume_facts(parsed, jd_skills=()):
    contact = parsed.get("contact", {})
    have = parsed.get("skills", {}).get("all", [])
    relevant = [s for s in have if s in set(jd_skills)] or have[:6]
    exp = parsed.get("experience", [])
    proj = parsed.get("projects", [])
    edu = parsed.get("education", [])
    return {
        "name": contact.get("name") or "",
        "skills": relevant[:8],
        "experience": [{"title": e.get("title"), "company": e.get("company"), "highlights": e.get("bullets", [])[:2]}
                       for e in exp[:2]],
        "projects": [{"name": p.get("name"), "technologies": p.get("technologies", [])[:4],
                      "summary": (p.get("description") or "")[:200]} for p in proj[:2]],
        "education": [{"degree": e.get("degree"), "institution": e.get("institution")} for e in edu[:1]],
    }


def template_letter(facts, company, position, tone):
    name = facts["name"] or "[Your Name]"
    skills = ", ".join(facts["skills"][:5]) or "[your most relevant skills]"
    opener = {
        "enthusiastic": f"I'm excited to apply for the {position} role at {company}.",
        "concise": f"I'm applying for the {position} role at {company}.",
        "technical": f"I'm applying for the {position} position at {company}, where I can apply my experience with {skills}.",
    }.get(tone, f"I am writing to apply for the {position} position at {company}.")
    paras = [f"Dear Hiring Manager,", opener]
    if facts["experience"]:
        e = facts["experience"][0]
        role_bits = " as " + e["title"] if e.get("title") else ""
        highlight = f" There, I {e['highlights'][0][0].lower() + e['highlights'][0][1:]}" if e.get("highlights") else ""
        paras.append(f"Most recently I worked at {e['company']}{role_bits}.{highlight.rstrip('.')}." if highlight else
                     f"Most recently I worked at {e['company']}{role_bits}.")
    if facts["projects"]:
        p = facts["projects"][0]
        techs = f" using {', '.join(p['technologies'])}" if p["technologies"] else ""
        paras.append(f"I also built {p['name']}{techs}, which strengthened my practical skills.")
    if facts["education"] and facts["education"][0].get("institution"):
        ed = facts["education"][0]
        paras.append(f"I studied {ed.get('degree') or ''} at {ed['institution']}.".replace("studied  at", "studied at"))
    paras.append(f"My skills in {skills} match what you're looking for, and I would welcome the chance to contribute to "
                 f"{company}. [Add one sentence about why this company specifically interests you.]")
    paras.append(f"Thank you for your time and consideration.\n\nSincerely,\n{name}")
    return "\n\n".join(paras)


def generate(user_id, parsed, company, position, tone, jd_text=None, jd_skills=()):
    tone = tone if tone in TONES else "formal"
    facts = resume_facts(parsed, jd_skills)
    ai = get_ai()
    if ai.available_for(user_id):
        try:
            res = ai.generate(
                service="cover_letter", user_id=user_id, schema=CoverLetterOut, system=SYSTEM_GUARDRAILS, temperature=0.7,
                prompt=(f"Write a {TONES[tone]} cover letter for the {position} role at {company}. Use ONLY these facts "
                        f"about the candidate: {facts}. Do not invent employers, projects, metrics, years of experience or "
                        "skills. If a motivating detail about the company is unknown, write a bracketed placeholder like "
                        "[why this company]. 3-4 paragraphs, ending with the candidate's name.\n\n"
                        f"<job_description>\n{(jd_text or 'Not provided')[:5000]}\n</job_description>"))
            return res.content, True, None
        except AIUnavailable as exc:
            return template_letter(facts, company, position, tone), False, exc.user_message + " Generated from a template."
    return template_letter(facts, company, position, tone), False, "AI unavailable - generated from a template using your resume facts."
