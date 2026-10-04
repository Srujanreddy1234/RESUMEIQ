"""/api/users (account, export, deletion) and /api/profile (career profile)."""
import io
import json

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import unset_jwt_cookies

from ..errors import ApiError, Conflict, NotFound
from ..extensions import db
from ..models import (AnalysisHistory, Application, CareerGoal, Certification, CoverLetter, Education, Experience,
                      InterviewSession, LearningProgress, Notification, Profile, Resume, SavedJob, SkillGap, User,
                      UserProject, UserSkill)
from ..security import current_user, get_owned, login_required, verify_password
from ..services import storage
from ..services.skill_extraction import canonical_skill, skill_rows
from .common import body
from .schemas import (AccountUpdateIn, CertificationIn, DeleteAccountIn, EducationIn, ExperienceIn, GoalIn, ProfileIn,
                      ProjectIn, UserSkillIn)

users_bp = Blueprint("users", __name__, url_prefix="/api/users")
bp = Blueprint("profile", __name__, url_prefix="/api/profile")


# ── Account ─────────────────────────────────────────────────────────────
@users_bp.get("/me")
@login_required
def get_me():
    user = current_user()
    return jsonify({"user": user.to_dict()})


@users_bp.patch("/me")
@login_required
def update_me():
    user = current_user()
    data = body(AccountUpdateIn)
    if data.full_name:
        user.full_name = data.full_name
    if data.email and data.email != user.email:
        if not data.current_password or not verify_password(data.current_password, user.password_hash):
            raise ApiError("Enter your current password to change your email.", status=400, code="invalid_password")
        if User.query.filter_by(email=data.email).first():
            raise Conflict("That email is already in use.", code="email_taken")
        user.email = data.email
    db.session.commit()
    return jsonify({"user": user.to_dict()})


@users_bp.get("/me/export")
@login_required
def export_data():
    """Download everything we store about the user (data portability)."""
    user = current_user()
    uid = user.id
    data = {
        "account": user.to_dict(),
        "profile": user.profile.to_dict() if user.profile else None,
        "career_goals": [g.to_dict() for g in CareerGoal.query.filter_by(user_id=uid)],
        "education": [e.to_dict() for e in Education.query.filter_by(user_id=uid)],
        "experience": [e.to_dict() for e in Experience.query.filter_by(user_id=uid)],
        "projects": [p.to_dict() for p in UserProject.query.filter_by(user_id=uid)],
        "certifications": [c.to_dict() for c in Certification.query.filter_by(user_id=uid)],
        "skills": [s.to_dict() for s in UserSkill.query.filter_by(user_id=uid)],
        "resumes": [{**r.to_dict(), "versions": [v.to_dict(include_parsed=True) for v in r.versions]}
                    for r in Resume.query.filter_by(user_id=uid)],
        "analyses": [a.to_dict() for a in AnalysisHistory.query.filter_by(user_id=uid)],
        "applications": [a.to_dict() for a in Application.query.filter_by(user_id=uid)],
        "saved_jobs": [{"job": s.job.to_dict(), "notes": s.notes} for s in SavedJob.query.filter_by(user_id=uid)],
        "cover_letters": [c.to_dict() for c in CoverLetter.query.filter_by(user_id=uid)],
        "interview_sessions": [s.to_dict() for s in InterviewSession.query.filter_by(user_id=uid)],
        "learning_progress": [p.to_dict() for p in LearningProgress.query.filter_by(user_id=uid)],
        "skill_gaps": [g.to_dict() for g in SkillGap.query.filter_by(user_id=uid)],
        "notifications": [n.to_dict() for n in Notification.query.filter_by(user_id=uid)],
    }
    buf = io.BytesIO(json.dumps(data, indent=2, default=str).encode())
    return send_file(buf, mimetype="application/json", as_attachment=True, download_name="resumeiq-data-export.json")


@users_bp.delete("/me")
@login_required
def delete_account():
    """Permanently delete the account and every stored file/row (cascades)."""
    user = current_user()
    data = body(DeleteAccountIn)
    if not verify_password(data.password, user.password_hash):
        raise ApiError("Password is incorrect.", status=400, code="invalid_password")
    files = [v.stored_filename for r in Resume.query.filter_by(user_id=user.id) for v in r.versions]
    if user.profile and user.profile.avatar_filename:
        files.append(user.profile.avatar_filename)
    db.session.delete(user)
    db.session.commit()
    for f in files:
        storage.delete_file(f)
    response = jsonify({"message": "Your account and all associated data have been permanently deleted."})
    unset_jwt_cookies(response)
    return response


# ── Profile ─────────────────────────────────────────────────────────────
def _profile(user):
    if user.profile is None:
        user.profile = Profile(user_id=user.id)
        db.session.flush()
    return user.profile


@bp.get("")
@login_required
def get_profile():
    user = current_user()
    profile = _profile(user)
    uid = user.id
    return jsonify({
        "user": user.to_dict(), "profile": profile.to_dict(),
        "goals": [g.to_dict() for g in CareerGoal.query.filter_by(user_id=uid).order_by(CareerGoal.is_primary.desc())],
        "education": [e.to_dict() for e in Education.query.filter_by(user_id=uid)],
        "experience": [e.to_dict() for e in Experience.query.filter_by(user_id=uid)],
        "projects": [p.to_dict() for p in UserProject.query.filter_by(user_id=uid)],
        "certifications": [c.to_dict() for c in Certification.query.filter_by(user_id=uid)],
        "skills": sorted([s.to_dict() for s in UserSkill.query.filter_by(user_id=uid)], key=lambda s: (-s["level"], s["skill"]["name"])),
    })


@bp.put("")
@login_required
def update_profile():
    user = current_user()
    profile = _profile(user)
    data = body(ProfileIn)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    if profile.salary_min and profile.salary_max and profile.salary_min > profile.salary_max:
        raise ApiError("Minimum salary can't exceed maximum salary.", status=422, code="validation_error")
    if data.target_career:
        goal = CareerGoal.query.filter_by(user_id=user.id, is_primary=True).first()
        if goal is None:
            db.session.add(CareerGoal(user_id=user.id, target_role=data.target_career, is_primary=True,
                                      weekly_hours=profile.weekly_study_hours))
        else:
            goal.target_role = data.target_career
    db.session.commit()
    return jsonify({"profile": profile.to_dict()})


@bp.post("/avatar")
@login_required
def upload_avatar():
    user = current_user()
    profile = _profile(user)
    data, ext, _ = storage.read_upload(request.files.get("avatar"), kind="image")
    name, _ = storage.save_bytes(data, ext)
    old = profile.avatar_filename
    profile.avatar_filename = name
    db.session.commit()
    storage.delete_file(old)
    return jsonify({"profile": profile.to_dict()})


@bp.get("/avatar")
@login_required
def get_avatar():
    profile = _profile(current_user())
    if not profile.avatar_filename:
        raise NotFound("Avatar")
    ext = profile.avatar_filename.rsplit(".", 1)[-1]
    response = send_file(storage.path_for(profile.avatar_filename), mimetype=storage.IMAGE_TYPES[ext], max_age=300)
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


@bp.delete("/avatar")
@login_required
def delete_avatar():
    profile = _profile(current_user())
    storage.delete_file(profile.avatar_filename)
    profile.avatar_filename = None
    db.session.commit()
    return jsonify({"profile": profile.to_dict()})


# ── Generic CRUD for profile sub-resources ───────────────────────────────
def _crud(name, model, schema):
    def create():
        user = current_user()
        data = body(schema)
        obj = model(user_id=user.id, **data.model_dump())
        if getattr(obj, "is_primary", False):
            model.query.filter_by(user_id=user.id).update({"is_primary": False})
        db.session.add(obj)
        db.session.commit()
        return jsonify(obj.to_dict()), 201

    def update(item_id):
        user = current_user()
        obj = get_owned(model, item_id, user, name)
        data = body(schema)
        for k, v in data.model_dump().items():
            setattr(obj, k, v)
        if hasattr(obj, "source"):
            obj.source = "manual"
        if getattr(obj, "is_primary", False):
            model.query.filter(model.user_id == user.id, model.id != obj.id).update({"is_primary": False})
            _profile(user).target_career = obj.target_role
        db.session.commit()
        return jsonify(obj.to_dict())

    def delete(item_id):
        obj = get_owned(model, item_id, current_user(), name)
        db.session.delete(obj)
        db.session.commit()
        return "", 204

    path = name.lower().replace(" ", "-")
    bp.add_url_rule(f"/{path}", f"create_{path}", login_required(create), methods=["POST"])
    bp.add_url_rule(f"/{path}/<int:item_id>", f"update_{path}", login_required(update), methods=["PUT"])
    bp.add_url_rule(f"/{path}/<int:item_id>", f"delete_{path}", login_required(delete), methods=["DELETE"])


_crud("Goals", CareerGoal, GoalIn)
_crud("Education", Education, EducationIn)
_crud("Experience", Experience, ExperienceIn)
_crud("Projects", UserProject, ProjectIn)
_crud("Certifications", Certification, CertificationIn)


@bp.post("/skills")
@login_required
def upsert_skill():
    """Add a skill or set its self-assessed level (1-5)."""
    user = current_user()
    data = body(UserSkillIn)
    name = canonical_skill(data.skill) or data.skill.strip()
    rows = skill_rows([name], create_unknown=True)
    if name not in rows:
        raise ApiError("That doesn't look like a valid skill name.", status=422, code="validation_error")
    us = UserSkill.query.filter_by(user_id=user.id, skill_id=rows[name].id).first()
    if us is None:
        us = UserSkill(user_id=user.id, skill_id=rows[name].id, level=data.level, source="self")
        db.session.add(us)
    else:
        us.level, us.source = data.level, "self"
    db.session.commit()
    return jsonify(us.to_dict()), 201


@bp.delete("/skills/<int:user_skill_id>")
@login_required
def delete_skill(user_skill_id):
    us = get_owned(UserSkill, user_skill_id, current_user(), "Skill")
    db.session.delete(us)
    db.session.commit()
    return "", 204
