"""/api/interview, /api/applications, /api/cover-letter."""
from flask import Blueprint, jsonify, request
from sqlalchemy import func

from ..errors import ApiError, NotFound
from ..extensions import db, limiter
from ..models import (STAGE_LABELS, STAGES, Application, ApplicationEvent, CoverLetter, InterviewQuestion,
                      InterviewSession, JobDescription, ResumeVersion)
from ..security import current_user, get_owned, login_required
from ..services import cover_letter as cover_service
from ..services import interview as interview_service
from ..services.resume_service import primary_version
from .common import body, pagination, paginate, user_or_ip
from .schemas import (AnswerIn, ApplicationIn, ApplicationPatch, CoverLetterIn, CoverLetterUpdate, InterviewIn, MoveIn)

interview_bp = Blueprint("interview", __name__, url_prefix="/api/interview")
apps_bp = Blueprint("applications", __name__, url_prefix="/api/applications")
cover_bp = Blueprint("cover_letter", __name__, url_prefix="/api/cover-letter")
AI_LIMIT = "20 per minute; 200 per day"


def _resolve_version(user, version_id):
    if version_id:
        v = db.session.get(ResumeVersion, version_id)
        if v is None or v.resume.user_id != user.id:
            raise NotFound("Resume version")
        return v
    return primary_version(user.id)


# ── Interview ───────────────────────────────────────────────────────────
@interview_bp.post("/sessions")
@login_required
@limiter.limit(AI_LIMIT, key_func=user_or_ip)
def create_session():
    user = current_user()
    data = body(InterviewIn)
    version = _resolve_version(user, data.resume_version_id)
    jd = get_owned(JobDescription, data.job_description_id, user, "Job description") if data.job_description_id else None
    session, ai_used, note = interview_service.create_session(
        user.id, data.mode, data.target_role, version.parsed_data if version else None,
        version.extracted_text if version else None, jd, version.id if version else None, data.categories, data.count)
    db.session.commit()
    return jsonify({"session": session.to_dict(), "ai_used": ai_used, "ai_note": note,
                    "next_question": interview_service.next_question(session)}), 201


@interview_bp.get("/sessions")
@login_required
def list_sessions():
    page, per_page = pagination(default=10)
    q = InterviewSession.query.filter_by(user_id=current_user().id).order_by(InterviewSession.created_at.desc())
    return jsonify(paginate(q, page, per_page, lambda s: s.to_dict(include_questions=False)))


@interview_bp.get("/sessions/<int:session_id>")
@login_required
def get_session(session_id):
    s = get_owned(InterviewSession, session_id, current_user(), "Interview session")
    return jsonify({"session": s.to_dict(), "next_question": interview_service.next_question(s)})


@interview_bp.post("/sessions/<int:session_id>/answers")
@login_required
@limiter.limit(AI_LIMIT, key_func=user_or_ip)
def answer(session_id):
    user = current_user()
    s = get_owned(InterviewSession, session_id, user, "Interview session")
    if s.status == "completed" and s.mode == "mock":
        raise ApiError("This mock interview is finished. Start a new one to continue practising.", status=409, code="session_completed")
    data = body(AnswerIn)
    q = db.session.get(InterviewQuestion, data.question_id)
    if q is None or q.session_id != s.id:
        raise NotFound("Question")
    result = interview_service.submit_answer(user.id, s, q, data.answer)
    db.session.commit()
    return jsonify(result)


@interview_bp.post("/sessions/<int:session_id>/finish")
@login_required
def finish(session_id):
    user = current_user()
    s = get_owned(InterviewSession, session_id, user, "Interview session")
    interview_service.finish_session(user.id, s)
    db.session.commit()
    return jsonify({"session": s.to_dict()})


@interview_bp.delete("/sessions/<int:session_id>")
@login_required
def delete_session(session_id):
    s = get_owned(InterviewSession, session_id, current_user(), "Interview session")
    db.session.delete(s)
    db.session.commit()
    return "", 204


# ── Applications (Kanban) ───────────────────────────────────────────────
def _record_stage(app, old):
    if old != app.stage:
        db.session.add(ApplicationEvent(application_id=app.id, from_stage=old, to_stage=app.stage))
        if app.stage == "applied" and app.date_applied is None:
            from datetime import date
            app.date_applied = date.today()


@apps_bp.get("")
@login_required
def board():
    user = current_user()
    q = Application.query.filter_by(user_id=user.id)
    if request.args.get("q"):
        like = f"%{request.args['q'][:80]}%"
        q = q.filter((Application.company.ilike(like)) | (Application.position.ilike(like)))
    apps = q.order_by(Application.board_position, Application.updated_at.desc()).limit(500).all()
    columns = [{"stage": s, "label": STAGE_LABELS[s], "items": [a.to_dict() for a in apps if a.stage == s]} for s in STAGES]
    return jsonify({"columns": columns, "total": len(apps)})


@apps_bp.post("")
@login_required
def create_app():
    user = current_user()
    data = body(ApplicationIn)
    pos = (db.session.query(func.coalesce(func.max(Application.board_position), -1))
           .filter_by(user_id=user.id, stage=data.stage).scalar() + 1)
    app = Application(user_id=user.id, board_position=pos, **data.model_dump())
    db.session.add(app)
    db.session.flush()
    _record_stage(app, None)
    db.session.commit()
    return jsonify(app.to_dict()), 201


@apps_bp.get("/<int:app_id>")
@login_required
def get_app(app_id):
    app = get_owned(Application, app_id, current_user(), "Application")
    return jsonify({**app.to_dict(), "history": [{"from": e.from_stage, "to": e.to_stage, "at": e.created_at.isoformat()}
                                                 for e in app.events]})


@apps_bp.patch("/<int:app_id>")
@login_required
def update_app(app_id):
    app = get_owned(Application, app_id, current_user(), "Application")
    old = app.stage
    for k, v in body(ApplicationPatch).model_dump(exclude_unset=True).items():
        if v is not None or k in ("notes", "interview_date", "contact_person", "contact_email", "salary", "job_url"):
            setattr(app, k, v)
    _record_stage(app, old)
    db.session.commit()
    return jsonify(app.to_dict())


@apps_bp.post("/<int:app_id>/move")
@login_required
def move(app_id):
    user = current_user()
    app = get_owned(Application, app_id, user, "Application")
    data = body(MoveIn)
    old = app.stage
    siblings = (Application.query.filter(Application.user_id == user.id, Application.stage == data.stage,
                                         Application.id != app.id).order_by(Application.board_position).all())
    siblings.insert(min(data.position, len(siblings)), app)
    for i, a in enumerate(siblings):
        a.board_position = i
    app.stage = data.stage
    _record_stage(app, old)
    db.session.commit()
    return jsonify(app.to_dict())


@apps_bp.delete("/<int:app_id>")
@login_required
def delete_app(app_id):
    app = get_owned(Application, app_id, current_user(), "Application")
    db.session.delete(app)
    db.session.commit()
    return "", 204


# ── Cover letters ───────────────────────────────────────────────────────
@cover_bp.post("")
@login_required
@limiter.limit(AI_LIMIT, key_func=user_or_ip)
def generate_letter():
    user = current_user()
    data = body(CoverLetterIn)
    version = _resolve_version(user, data.resume_version_id)
    if version is None:
        raise ApiError("Upload a resume first - cover letters are built only from your real experience.",
                       status=400, code="resume_required")
    jd_text, jd_skills = data.job_description, []
    if data.job_description_id:
        jd = get_owned(JobDescription, data.job_description_id, user, "Job description")
        jd_text, jd_skills = jd.raw_text, jd.parsed.get("required_skills", []) + jd.parsed.get("preferred_skills", [])
    elif jd_text:
        from ..services.skill_extraction import extract_skills
        jd_skills = list(extract_skills(jd_text))
    content, ai_used, note = cover_service.generate(user.id, version.parsed_data, data.company, data.position, data.tone,
                                                    jd_text, jd_skills)
    letter = CoverLetter(user_id=user.id, resume_version_id=version.id, job_description_id=data.job_description_id,
                         company=data.company, position=data.position, tone=data.tone, content=content, ai_used=ai_used)
    db.session.add(letter)
    db.session.commit()
    return jsonify({**letter.to_dict(), "ai_note": note}), 201


@cover_bp.get("")
@login_required
def list_letters():
    page, per_page = pagination(default=20)
    q = CoverLetter.query.filter_by(user_id=current_user().id).order_by(CoverLetter.updated_at.desc())
    return jsonify(paginate(q, page, per_page, lambda c: c.to_dict()))


@cover_bp.get("/<int:letter_id>")
@login_required
def get_letter(letter_id):
    return jsonify(get_owned(CoverLetter, letter_id, current_user(), "Cover letter").to_dict())


@cover_bp.put("/<int:letter_id>")
@login_required
def update_letter(letter_id):
    letter = get_owned(CoverLetter, letter_id, current_user(), "Cover letter")
    data = body(CoverLetterUpdate)
    letter.content = data.content
    if data.company:
        letter.company = data.company
    if data.position:
        letter.position = data.position
    db.session.commit()
    return jsonify(letter.to_dict())


@cover_bp.delete("/<int:letter_id>")
@login_required
def delete_letter(letter_id):
    letter = get_owned(CoverLetter, letter_id, current_user(), "Cover letter")
    db.session.delete(letter)
    db.session.commit()
    return "", 204
