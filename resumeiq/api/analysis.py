"""/api/analysis (resume analysis, history, ATS, improvement) and /api/job-descriptions."""
from flask import Blueprint, jsonify, request

from ..errors import NotFound
from ..extensions import db, limiter
from ..models import AnalysisHistory, BackgroundTask, JobDescription, ResumeVersion
from ..security import current_user, get_owned, login_required
from ..services import improvement, tasks
from ..services.ai import SYSTEM_GUARDRAILS, AIUnavailable, get_ai
from ..services.ai.schemas import ResumeTips
from ..services.ats import analyze_ats
from ..services.jd_service import analyze_job_description
from ..services.resume_service import ANALYSIS_STAGES, primary_version, run_analysis
from .common import body, pagination, paginate, user_or_ip
from .schemas import AnalysisIn, ATSIn, ImproveIn, JDIn

bp = Blueprint("analysis", __name__, url_prefix="/api/analysis")
jd_bp = Blueprint("job_descriptions", __name__, url_prefix="/api/job-descriptions")
tasks_bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")
AI_LIMIT = "20 per minute; 200 per day"


def _version(version_id, user):
    v = db.session.get(ResumeVersion, version_id)
    if v is None or v.resume.user_id != user.id:
        raise NotFound("Resume version")
    return v


@bp.post("")
@login_required
@limiter.limit(AI_LIMIT, key_func=user_or_ip)
def start_analysis():
    """Start an async analysis. Poll GET /api/tasks/<id> for real stage-by-stage progress."""
    user = current_user()
    data = body(AnalysisIn)
    _version(data.resume_version_id, user)
    if data.job_description_id:
        get_owned(JobDescription, data.job_description_id, user, "Job description")
    task = tasks.submit(user.id, "resume_analysis", ANALYSIS_STAGES, run_analysis, user.id, data.resume_version_id,
                        data.target_role, data.job_description_id)
    return jsonify({"task": task.to_dict()}), 202


@tasks_bp.get("/<task_id>")
@login_required
def task_status(task_id):
    task = db.session.get(BackgroundTask, task_id)
    if task is None or task.user_id != current_user().id:
        raise NotFound("Task")
    return jsonify(task.to_dict())


@bp.get("")
@login_required
def history():
    user = current_user()
    page, per_page = pagination(default=15)
    q = AnalysisHistory.query.filter_by(user_id=user.id)
    if request.args.get("kind"):
        q = q.filter(AnalysisHistory.kind == request.args["kind"])
    if request.args.get("role"):
        q = q.filter(AnalysisHistory.target_role.ilike(f"%{request.args['role']}%"))
    if request.args.get("resume_id"):
        q = q.join(ResumeVersion, AnalysisHistory.resume_version_id == ResumeVersion.id).filter(
            ResumeVersion.resume_id == int(request.args["resume_id"]))
    q = q.order_by(AnalysisHistory.created_at.desc())
    return jsonify(paginate(q, page, per_page, lambda a: a.to_summary()))


@bp.get("/<int:analysis_id>")
@login_required
def get_analysis(analysis_id):
    return jsonify(get_owned(AnalysisHistory, analysis_id, current_user(), "Analysis").to_dict())


@bp.delete("/<int:analysis_id>")
@login_required
def delete_analysis(analysis_id):
    a = get_owned(AnalysisHistory, analysis_id, current_user(), "Analysis")
    db.session.delete(a)
    db.session.commit()
    return "", 204


@bp.delete("")
@login_required
def delete_all_history():
    deleted = AnalysisHistory.query.filter_by(user_id=current_user().id).delete()
    db.session.commit()
    return jsonify({"deleted": deleted})


@bp.post("/ats")
@login_required
@limiter.limit(AI_LIMIT, key_func=user_or_ip)
def ats():
    user = current_user()
    data = body(ATSIn)
    version = _version(data.resume_version_id, user)
    if data.job_description_id:
        jd = get_owned(JobDescription, data.job_description_id, user, "Job description")
    else:
        if not data.job_description or len(data.job_description.split()) < 15:
            from ..errors import ValidationFailed
            raise ValidationFailed("Paste the full job description (at least a few sentences).",
                                   details=[{"field": "job_description", "message": "Job description is too short."}])
        jd = analyze_job_description(user.id, data.job_title, data.job_description, data.company)
    profile_years = user.profile.years_experience if user.profile else None
    result = analyze_ats(version.parsed_data, version.extracted_text, version.file_type, jd.parsed, data.job_title,
                         user.profile.target_career if user.profile else None, profile_years)
    analysis = AnalysisHistory(user_id=user.id, resume_version_id=version.id, job_description_id=jd.id, kind="ats",
                               target_role=data.job_title[:120], overall_score=result["ats_score"],
                               score_breakdown=result["components"], result=result,
                               skills_identified=len(version.parsed_data["skills"]["all"]), ai_used=jd.ai_used)
    db.session.add(analysis)
    db.session.commit()
    return jsonify({"analysis_id": analysis.id, "job_description": jd.to_dict(), **result})


@bp.post("/improve")
@login_required
@limiter.limit(AI_LIMIT, key_func=user_or_ip)
def improve():
    user = current_user()
    data = body(ImproveIn)
    version = _version(data.resume_version_id, user)
    if data.scope == "bullet" and not data.bullet:
        from ..errors import ValidationFailed
        raise ValidationFailed("Provide the bullet text to improve.", details=[{"field": "bullet", "message": "Required"}])
    result = improvement.improve(version.parsed_data, version.extracted_text, data.scope, user.id,
                                 data.target_role or (user.profile.target_career if user.profile else None), data.bullet)
    weak = improvement.weak_bullets(version.parsed_data) if data.scope != "bullet" else []
    return jsonify({**result, "weak_bullets": weak})


@bp.post("/tips")
@login_required
@limiter.limit(AI_LIMIT, key_func=user_or_ip)
def resume_tips():
    """Role-specific resume tips (carried over from the original app)."""
    user = current_user()
    role = (request.get_json(silent=True) or {}).get("job_role", "").strip()[:120] or "software engineering"
    try:
        res = get_ai().generate(service="resume_tips", user_id=user.id, schema=ResumeTips, system=SYSTEM_GUARDRAILS,
                                prompt=f"Give 8 specific, practical resume-writing tips for a {role} position.")
        return jsonify({"tips": res.tips[:10], "ai_used": True})
    except AIUnavailable as exc:
        tips = ["Lead each bullet with a strong action verb.", "Add real, verifiable results where you have them.",
                f"Mirror the exact skill names used in {role} job postings you are targeting.",
                "Use standard headings: Experience, Projects, Education, Skills.",
                "Keep it to one page if you have under five years of experience.",
                "Put your strongest, most relevant project near the top.",
                "List technologies inside each project/experience entry, not only in a skills list.",
                "Remove outdated or irrelevant content so key points stand out."]
        return jsonify({"tips": tips, "ai_used": False, "ai_note": exc.user_message})


# ── Job descriptions ─────────────────────────────────────────────────────
@jd_bp.post("")
@login_required
@limiter.limit(AI_LIMIT, key_func=user_or_ip)
def create_jd():
    """Analyse a pasted job description and compare it with the primary (or given) resume."""
    user = current_user()
    data = body(JDIn)
    jd = analyze_job_description(user.id, data.title, data.text, data.company)
    version_id = request.args.get("resume_version_id", type=int)
    version = _version(version_id, user) if version_id else primary_version(user.id)
    comparison = None
    if version is not None:
        comparison = analyze_ats(version.parsed_data, version.extracted_text, version.file_type, jd.parsed, data.title,
                                 user.profile.target_career if user.profile else None,
                                 user.profile.years_experience if user.profile else None)
        db.session.add(AnalysisHistory(user_id=user.id, resume_version_id=version.id, job_description_id=jd.id,
                                       kind="jd_match", target_role=data.title[:120], overall_score=comparison["ats_score"],
                                       score_breakdown=comparison["components"], result=comparison,
                                       skills_identified=len(version.parsed_data["skills"]["all"]), ai_used=jd.ai_used))
    db.session.commit()
    return jsonify({"job_description": jd.to_dict(), "comparison": comparison,
                    "resume": version.to_dict() if version else None}), 201


@jd_bp.get("")
@login_required
def list_jds():
    page, per_page = pagination(default=20)
    q = JobDescription.query.filter_by(user_id=current_user().id).order_by(JobDescription.created_at.desc())
    return jsonify(paginate(q, page, per_page, lambda j: j.to_dict()))


@jd_bp.get("/<int:jd_id>")
@login_required
def get_jd(jd_id):
    return jsonify(get_owned(JobDescription, jd_id, current_user(), "Job description").to_dict(include_text=True))


@jd_bp.delete("/<int:jd_id>")
@login_required
def delete_jd(jd_id):
    jd = get_owned(JobDescription, jd_id, current_user(), "Job description")
    db.session.delete(jd)
    db.session.commit()
    return "", 204
