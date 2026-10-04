"""Resume improvement suggestions.

Hard rule: never invent achievements or numbers. Any number in an improved
bullet that is not present in the original is replaced by a placeholder and
the item is flagged "Add a measurable result here".
"""
import re

from .ai import SYSTEM_GUARDRAILS, AIUnavailable, get_ai
from .ai.schemas import ImprovementResult
from .resume_parser import ACTION_VERBS, WEAK_OPENERS, has_metric

NUMBER_RX = re.compile(r"\d+(?:[.,]\d+)*\s?%?")
PLACEHOLDER = "[add measurable result]"

WEAK_REWRITES = [
    (re.compile(r"^(?:worked on|was involved in|involved in|participated in)\s+", re.I), "Contributed to "),
    (re.compile(r"^responsible for\s+", re.I), "Owned "),
    (re.compile(r"^(?:helped|assisted)(?:\s+(?:with|in))?\s+", re.I), "Supported "),
    (re.compile(r"^made\s+", re.I), "Built "),
    (re.compile(r"^did\s+", re.I), "Performed "),
    (re.compile(r"^handled\s+", re.I), "Managed "),
    (re.compile(r"^tasked with\s+", re.I), "Delivered "),
]


def numbers_in(text):
    return {re.sub(r"[\s,]", "", n) for n in NUMBER_RX.findall(text or "")}


def guard_fabrication(original, improved):
    """Replace numbers that don't appear in the original. Returns (text, fabricated_flag)."""
    allowed = numbers_in(original)
    fabricated = False

    def repl(m):
        nonlocal fabricated
        if re.sub(r"[\s,]", "", m.group(0)) in allowed:
            return m.group(0)
        fabricated = True
        return "[X]"

    guarded = NUMBER_RX.sub(repl, improved)
    return guarded, fabricated


def weak_bullets(parsed, limit=12):
    items = []
    for b in parsed.get("bullets", []):
        text = b["text"].strip()
        reasons = []
        if WEAK_OPENERS.match(text):
            reasons.append("starts with weak phrasing")
        first = re.match(r"\s*([A-Za-z]+)", text)
        if first and first.group(1).lower() not in ACTION_VERBS and not WEAK_OPENERS.match(text):
            reasons.append("doesn't start with a strong action verb")
        if not has_metric(text):
            reasons.append("no measurable outcome")
        if len(text.split()) < 7:
            reasons.append("too brief to show scope")
        if reasons:
            items.append({**b, "reasons": reasons})
    items.sort(key=lambda x: -len(x["reasons"]))
    return items[:limit]


def rule_based_rewrite(text):
    improved = text.strip().rstrip(".")
    for rx, replacement in WEAK_REWRITES:
        if rx.match(improved):
            improved = rx.sub(replacement, improved, count=1)
            break
    improved = improved[0].upper() + improved[1:] if improved else improved
    needs_metric = not has_metric(improved)
    if needs_metric:
        improved += f", resulting in {PLACEHOLDER}"
    return improved + ".", needs_metric


def improve(parsed, resume_text, scope, user_id, target_role=None, bullet_text=None):
    """scope: entire | bullet | summary | skills | projects | experience"""
    if scope == "bullet":
        candidates = [{"text": bullet_text, "section": "custom", "reasons": []}]
    else:
        candidates = weak_bullets(parsed, limit=15)
        if scope in ("projects", "experience"):
            candidates = [c for c in candidates if c["section"] == scope]
        elif scope in ("summary", "skills"):
            candidates = []

    ai_used, ai_note = False, None
    items, improved_summary, skills_advice = [], None, []
    ai = get_ai()
    if ai.available_for(user_id):
        try:
            result = _ai_improve(candidates, parsed, resume_text, scope, user_id, target_role)
            ai_used = True
            originals = {c["text"] for c in candidates}
            for item in result.items:
                if scope != "bullet" and item.original not in originals and item.original not in resume_text:
                    continue  # AI rewrote something that isn't in the resume
                guarded, fabricated = guard_fabrication(item.original, item.improved)
                needs_metric = item.needs_metric or fabricated or not has_metric(item.original)
                if needs_metric and PLACEHOLDER not in guarded and "[X]" not in guarded:
                    guarded = guarded.rstrip(".") + f" ({PLACEHOLDER})."
                items.append({"section": item.section, "original": item.original, "improved": guarded,
                              "explanation": item.explanation + (" Numbers not in your original were removed - add only "
                                                                 "real figures." if fabricated else ""),
                              "needs_metric": needs_metric})
            if result.improved_summary:
                improved_summary, _ = guard_fabrication(parsed.get("summary") or "", result.improved_summary)
            skills_advice = result.skills_section_advice
        except AIUnavailable as exc:
            ai_note = exc.user_message + " Showing rule-based rewrites."
    else:
        ai_note = "AI unavailable - showing rule-based rewrites."

    if not ai_used:
        for c in candidates:
            improved, needs_metric = rule_based_rewrite(c["text"])
            items.append({"section": c["section"], "original": c["text"], "improved": improved,
                          "explanation": "Rewritten to lead with an action verb"
                                         + (" - add a real measurable result where the placeholder is." if needs_metric else "."),
                          "needs_metric": needs_metric})
        if scope in ("summary", "entire"):
            improved_summary = None
        if scope in ("skills", "entire"):
            skills_advice = _skills_advice(parsed)

    return {"scope": scope, "items": items, "improved_summary": improved_summary,
            "skills_section_advice": skills_advice, "ai_used": ai_used, "ai_note": ai_note,
            "rule": "We never invent achievements or numbers. Placeholders mark where you should add a real result."}


def _skills_advice(parsed):
    by_cat = parsed["skills"]["by_category"]
    advice = ["Group skills by category (Languages, Frameworks, Databases, Tools, Cloud) so they're easy to scan."]
    if len(parsed["skills"]["all"]) > 30:
        advice.append("Trim the list to skills you could discuss confidently in an interview.")
    if not by_cat.get("cloud_devops"):
        advice.append("If you've used Git, Docker or a cloud platform, list them explicitly.")
    return advice


def _ai_improve(candidates, parsed, resume_text, scope, user_id, target_role):
    listing = "\n".join(f"- [{c['section']}] {c['text']}" for c in candidates) or "(none)"
    prompt = (
        f"Target role: {target_role or 'not specified'}\nScope: {scope}\n\n"
        "Rewrite the bullets below to be stronger: lead with an action verb, state the technology and scope, "
        "and keep every fact that is in the original. STRICT RULES: do not add numbers, percentages, metrics, "
        "tools or achievements that are not in the original bullet or the resume. If a measurable result would help "
        "but isn't provided, set needs_metric=true and write '[add measurable result]' where it belongs. "
        "Copy each original exactly into `original`.\n"
        + ("Also write an improved 2-3 sentence professional summary using only facts in the resume.\n"
           if scope in ("summary", "entire") else "")
        + ("Also give advice on organising the skills section.\n" if scope in ("skills", "entire") else "")
        + f"\nBullets to improve:\n{listing}\n\n<resume>\n{resume_text[:10000]}\n</resume>"
    )
    return get_ai().generate(service="resume_improvement", prompt=prompt, schema=ImprovementResult, user_id=user_id,
                             temperature=0.4, system=SYSTEM_GUARDRAILS)
