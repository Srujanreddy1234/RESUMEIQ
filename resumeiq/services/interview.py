"""InterviewService: question generation, answer evaluation, mock-interview flow and reports.

Evaluations are based only on the text of the answer. We report text-based
indicators (length, hedging phrases, structure) and never judge personality,
emotions or mental state.
"""
import re

from ..extensions import db
from ..models import InterviewAnswer, InterviewQuestion, InterviewSession, utcnow
from .ai import SYSTEM_GUARDRAILS, AIUnavailable, get_ai
from .ai.schemas import AnswerEvaluation, InterviewQuestionSet, InterviewSummary
from .skill_extraction import SKILL_BY_NAME, role_requirements

CATEGORIES = ("technical", "behavioral", "hr", "project", "system_design", "dsa")
HEDGES = re.compile(r"\b(i think|i guess|maybe|probably|not sure|kind of|sort of|i believe|perhaps|might be|i suppose)\b", re.I)
FILLERS = re.compile(r"\b(um+|uh+|you know|basically|literally|like,)\b", re.I)
STAR = {"situation": re.compile(r"\b(situation|context|when i was|at my|during|while working)\b", re.I),
        "task": re.compile(r"\b(task|goal|needed to|responsible|challenge|problem was)\b", re.I),
        "action": re.compile(r"\b(i (built|designed|implemented|decided|wrote|led|created|added|fixed|analy[sz]ed|refactored|used))\b", re.I),
        "result": re.compile(r"\b(result|outcome|as a result|which (led|reduced|improved|increased)|ended up|learned)\b", re.I)}

BANK = {
    "behavioral": [
        ("Tell me about a time you faced a difficult technical problem. How did you solve it?",
         "Assesses problem-solving process and ownership.",
         ["A specific situation and why it was hard", "The concrete steps you took and alternatives considered",
          "The measurable or observable result", "What you learned"],
         ["Staying vague or hypothetical", "Describing what 'we' did without your own contribution", "No result"]),
        ("Describe a time you disagreed with a teammate. What happened?",
         "Checks collaboration and conflict-resolution skills.",
         ["Respectful framing of the disagreement", "How you listened and used evidence", "The resolution and relationship afterwards"],
         ["Blaming others", "Claiming you've never disagreed", "No resolution"]),
        ("Tell me about a time you missed a deadline or made a mistake.",
         "Looks for accountability and learning.",
         ["Own the mistake clearly", "What you did to mitigate impact", "What you changed to prevent it recurring"],
         ["Choosing a fake weakness", "Deflecting blame", "No lesson learned"]),
        ("Give an example of when you had to learn a new technology quickly.",
         "Assesses learning ability, important for early-career engineers.",
         ["Why you had to learn it", "Your learning approach and resources", "What you built with it and the outcome"],
         ["Listing tutorials without applying them", "No concrete outcome"]),
    ],
    "hr": [
        ("Why are you interested in this role?", "Checks motivation and whether you understand the role.",
         ["Specific aspects of the role/company", "How your skills and goals align", "What you hope to contribute"],
         ["Generic answers that fit any company", "Focusing only on salary or perks"]),
        ("Where do you see yourself in three to five years?", "Gauges ambition and fit with growth paths.",
         ["Realistic growth in skills and responsibility", "Connection to this role"], ["Saying you want the interviewer's job", "No direction"]),
        ("What are your salary expectations?", "Checks alignment with the budgeted range.",
         ["A researched range", "Flexibility based on the full package"], ["Naming a number with no research", "Refusing to engage at all"]),
    ],
    "system_design": [
        ("Design a URL shortener. How would you handle high read traffic?", "Tests system-design fundamentals at an approachable scale.",
         ["Clarify requirements and scale", "API and data model", "Key generation strategy", "Caching for hot links", "Scaling the database"],
         ["Jumping into details before requirements", "Ignoring collisions or caching"]),
        ("How would you design a rate limiter for a public API?", "Probes knowledge of algorithms and distributed state.",
         ["Token bucket / sliding window trade-offs", "Where state lives (e.g. Redis)", "Per-user vs per-IP limits", "Response codes and headers"],
         ["Only in-memory state for multiple servers", "No discussion of trade-offs"]),
    ],
    "dsa": [
        ("Given an array of integers and a target, return indices of two numbers that sum to the target. Discuss complexity.",
         "Classic hash-map problem testing complexity analysis.",
         ["Brute force O(n^2) first", "Hash map single pass O(n) time, O(n) space", "Edge cases (duplicates, no solution)"],
         ["Not stating complexity", "Missing edge cases"]),
        ("How would you detect a cycle in a linked list?", "Tests pointer techniques.",
         ["Floyd's tortoise and hare", "O(n) time, O(1) space", "Alternative with a hash set"], ["Only the hash-set solution without trade-offs"]),
        ("Explain the difference between BFS and DFS and when you'd use each.", "Tests graph traversal fundamentals.",
         ["Queue vs stack/recursion", "Shortest path in unweighted graphs uses BFS", "Memory characteristics"], ["Confusing the two"]),
    ],
}


def _technical_from_skill(skill):
    meta = SKILL_BY_NAME.get(skill, {})
    topics = meta.get("topics", [])
    return (f"Explain how you have used {skill}. What are its key concepts and trade-offs?",
            f"Verifies the depth of {skill} knowledge claimed on your resume or required by the role.",
            [f"A concrete example of using {skill}"] + [f"Understanding of: {t}" for t in topics[:3]]
            + ["Trade-offs or limitations"],
            ["Reciting definitions without experience", "Overstating proficiency"])


def _project_question(project):
    return (f"Walk me through your project '{project.get('name')}'. What was the hardest technical decision?",
            "Interviewers use your own projects to judge depth and ownership.",
            ["Problem and motivation", "Architecture and technology choices with reasons",
             "A difficult decision or bug and how you handled it", "Results and what you'd improve"],
            ["Only listing technologies", "Unable to explain design choices", "Claiming team work as solely yours"])


def fallback_questions(role, parsed, categories, count):
    _, reqs = role_requirements(role, parsed.get("skills", {}).get("all", []) if parsed else [])
    skills = [r["skill"] for r in reqs if r["importance"] in ("core", "important")][:6] or (
        parsed.get("skills", {}).get("all", [])[:6] if parsed else [])
    pools = {
        "technical": [_technical_from_skill(s) for s in skills],
        "project": [_project_question(p) for p in (parsed or {}).get("projects", [])[:3]],
        **{k: v for k, v in BANK.items()},
    }
    out = []
    i = 0
    while len(out) < count and any(pools.get(c) for c in categories):
        cat = categories[i % len(categories)]
        if pools.get(cat):
            q, why, points, mistakes = pools[cat].pop(0)
            out.append({"category": cat, "difficulty": "medium", "question": q, "why_asked": why,
                        "strong_answer_points": points, "common_mistakes": mistakes})
        i += 1
        if i > count * 10:
            break
    return out


def generate_questions(user_id, role, parsed, resume_text, jd_text, categories, count):
    categories = [c for c in categories if c in CATEGORIES] or ["technical", "behavioral", "project"]
    ai = get_ai()
    if ai.available_for(user_id):
        try:
            res = ai.generate(
                service="interview_questions", user_id=user_id, schema=InterviewQuestionSet, system=SYSTEM_GUARDRAILS,
                temperature=0.6,
                prompt=(f"Create {count} interview questions for a '{role}' candidate, spread across these categories: "
                        f"{', '.join(categories)}. Ground technical and project questions in the resume and job "
                        "description. For each give: why the interviewer asks it, what a strong answer contains "
                        "(3-5 points), and common mistakes (2-3).\n\n"
                        f"<resume>\n{(resume_text or '')[:8000]}\n</resume>\n"
                        f"<job_description>\n{(jd_text or 'Not provided')[:5000]}\n</job_description>"))
            qs = [q.model_dump() for q in res.questions if q.category in categories][:count]
            if qs:
                return qs, True, None
        except AIUnavailable as exc:
            return fallback_questions(role, parsed, categories, count), False, exc.user_message
    return fallback_questions(role, parsed, categories, count), False, "AI unavailable - using the curated question bank."


def create_session(user_id, mode, role, parsed, resume_text, jd, resume_version_id, categories, count):
    questions, ai_used, note = generate_questions(user_id, role, parsed, resume_text, jd.raw_text if jd else None,
                                                  categories, count)
    session = InterviewSession(user_id=user_id, mode=mode, target_role=role[:120], categories=categories,
                               job_description_id=jd.id if jd else None, resume_version_id=resume_version_id,
                               max_questions=len(questions))
    db.session.add(session)
    db.session.flush()
    for pos, q in enumerate(questions):
        db.session.add(InterviewQuestion(session_id=session.id, position=pos * 10, category=q["category"],
                                         difficulty=q.get("difficulty", "medium"), question=q["question"],
                                         why_asked=q.get("why_asked"), strong_answer_points=q.get("strong_answer_points", []),
                                         common_mistakes=q.get("common_mistakes", [])))
    db.session.flush()
    return session, ai_used, note


# ── Evaluation ───────────────────────────────────────────────────────────
def text_indicators(answer):
    words = re.findall(r"\b\w+\b", answer)
    sentences = [s for s in re.split(r"[.!?]+", answer) if s.strip()]
    star = {k: bool(rx.search(answer)) for k, rx in STAR.items()}
    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "hedging_phrases": len(HEDGES.findall(answer)),
        "filler_words": len(FILLERS.findall(answer)),
        "uses_examples": bool(re.search(r"\b(for example|for instance|in my project|at my internship|when i)\b", answer, re.I)),
        "includes_numbers": bool(re.search(r"\d", answer)),
        "star_elements": star,
        "first_person_ownership": len(re.findall(r"\bI\b", answer)),
        "note": "Text-based indicators only. They are not judgments of personality, confidence or ability.",
    }


def _coverage(answer, points):
    if not points:
        return 0.5, []
    lowered = answer.lower()
    missing = []
    hit = 0
    for p in points:
        terms = [t for t in re.findall(r"[a-z][a-z0-9+#]{3,}", p.lower()) if t not in {"with", "your", "that", "what", "about"}]
        if terms and sum(1 for t in terms if t in lowered) / len(terms) >= 0.34:
            hit += 1
        else:
            missing.append(p)
    return hit / len(points), missing


def heuristic_evaluation(question, answer):
    ind = text_indicators(answer)
    cov, missing = _coverage(answer, question.strong_answer_points)
    wc = ind["word_count"]
    length_ok = 1.0 if 60 <= wc <= 300 else 0.6 if 30 <= wc < 60 or 300 < wc <= 450 else 0.25
    star_n = sum(ind["star_elements"].values())
    structure = (star_n / 4) if question.category in ("behavioral", "hr", "project") else min(1, ind["sentence_count"] / 5)
    scores = {
        "communication": round(10 * max(0, length_ok - min(ind["filler_words"], 5) * 0.05)),
        "technical_accuracy": round(10 * (0.3 + 0.7 * cov)) if question.category in ("technical", "system_design", "dsa", "project")
        else round(10 * (0.4 + 0.6 * cov)),
        "relevance": round(10 * (0.25 + 0.75 * cov)),
        "structure": round(10 * (0.3 + 0.7 * structure)),
    }
    tips = []
    if wc < 60:
        tips.append("Expand your answer with a specific example and its outcome.")
    if question.category in ("behavioral", "project") and star_n < 3:
        tips.append("Use the STAR structure: Situation, Task, Action, Result.")
    if ind["hedging_phrases"] >= 3:
        tips.append("State conclusions directly where you're sure; reserve hedging for genuine uncertainty.")
    if missing:
        tips.append("Cover: " + "; ".join(missing[:3]))
    return {"scores": scores, "feedback": "Rule-based evaluation: compared your answer against the key points a strong answer "
                                          "usually contains.", "missing_concepts": missing[:5], "improvements": tips,
            "follow_up_question": None, "method": "heuristic", "indicators": ind}


def evaluate_answer(user_id, question, answer, allow_follow_up):
    ai = get_ai()
    if ai.available_for(user_id):
        try:
            res = ai.generate(
                service="interview_evaluation", user_id=user_id, schema=AnswerEvaluation, system=SYSTEM_GUARDRAILS,
                temperature=0.2,
                prompt=(f"Question ({question.category}): {question.question}\nA strong answer covers: "
                        f"{'; '.join(question.strong_answer_points)}\n\nEvaluate ONLY the content of the text answer. "
                        "Score communication, technical_accuracy, relevance and structure from 0-10. List concepts that "
                        "are missing and concrete improvements. "
                        + ("If useful, propose ONE natural follow-up question an interviewer would ask next; otherwise null. "
                           if allow_follow_up else "Set follow_up_question to null. ")
                        + "Do not comment on personality, emotions or confidence as a trait.\n\n"
                        f"<answer>\n{answer[:6000]}\n</answer>"))
            return {**res.model_dump(), "scores": res.scores.model_dump(), "method": "ai", "indicators": text_indicators(answer)}
        except AIUnavailable:
            pass
    return heuristic_evaluation(question, answer)


def submit_answer(user_id, session, question, answer):
    is_mock = session.mode == "mock"
    follow_ups = sum(1 for q in session.questions if q.is_follow_up)
    allow_follow = is_mock and not question.is_follow_up and follow_ups < 3
    result = evaluate_answer(user_id, question, answer, allow_follow)
    overall = round(sum(result["scores"].values()) / 4 * 10)
    db.session.add(InterviewAnswer(question_id=question.id, user_id=user_id, answer_text=answer[:10000],
                                   scores=result["scores"], overall_score=overall, feedback=result["feedback"],
                                   missing_concepts=result["missing_concepts"],
                                   textual_indicators={**result["indicators"], "improvements": result["improvements"]},
                                   evaluation_method=result["method"]))
    follow = None
    if allow_follow and result.get("follow_up_question"):
        follow = InterviewQuestion(session_id=session.id, position=question.position + 1, category=question.category,
                                   difficulty=question.difficulty, question=result["follow_up_question"][:1000],
                                   why_asked="Follow-up on your previous answer.", strong_answer_points=[],
                                   common_mistakes=[], parent_question_id=question.id, is_follow_up=True)
        db.session.add(follow)
    db.session.flush()
    db.session.refresh(session)
    return {"evaluation": {**result, "overall_score": overall}, "follow_up": follow.to_dict() if follow else None,
            "next_question": next_question(session)}


def next_question(session):
    for q in session.questions:
        if not q.answers:
            return q.to_dict()
    return None


def finish_session(user_id, session):
    answered = [q for q in session.questions if q.answers]
    if not answered:
        session.status = "completed"
        session.completed_at = utcnow()
        session.summary = {"note": "No answers were submitted."}
        return session
    dims = ("communication", "technical_accuracy", "relevance", "structure")
    avgs = {d: round(sum(q.answers[-1].scores.get(d, 0) for q in answered) / len(answered) * 10) for d in dims}
    missing = list(dict.fromkeys(m for q in answered for m in q.answers[-1].missing_concepts))[:10]
    improvements = list(dict.fromkeys(i for q in answered for i in q.answers[-1].textual_indicators.get("improvements", [])))[:8]
    hedges = sum(q.answers[-1].textual_indicators.get("hedging_phrases", 0) for q in answered)
    words = [q.answers[-1].textual_indicators.get("word_count", 0) for q in answered]
    summary = {"scores": avgs, "missing_concepts": missing, "improvements": improvements,
               "answered": len(answered), "total": len(session.questions),
               "text_indicators": {"avg_words_per_answer": round(sum(words) / len(words)), "hedging_phrases_total": hedges,
                                   "note": "Indicators are computed from your typed text only. They are not assessments "
                                           "of personality, confidence or mental state."},
               "ai_summary": None}
    ai = get_ai()
    if ai.available_for(user_id):
        try:
            transcript = "\n\n".join(f"Q: {q.question}\nA: {q.answers[-1].answer_text[:1500]}" for q in answered)
            res = ai.generate(service="interview_summary", user_id=user_id, schema=InterviewSummary, system=SYSTEM_GUARDRAILS,
                              temperature=0.3,
                              prompt=(f"Summarise this {session.target_role} mock interview. Scores (0-100): {avgs}. "
                                      "Give a short summary, strengths, improvements and missing concepts, based only on "
                                      f"the text.\n\n<answer>\n{transcript[:12000]}\n</answer>"))
            summary["ai_summary"] = res.model_dump()
        except AIUnavailable:
            pass
    session.summary = summary
    session.overall_score = round(sum(avgs.values()) / len(avgs))
    session.status = "completed"
    session.completed_at = utcnow()
    db.session.flush()
    return session
