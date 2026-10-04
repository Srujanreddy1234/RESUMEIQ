"""/api/resumes - multi-resume storage, versioning, download, comparison."""
from flask import Blueprint, current_app, jsonify, request, send_file

from ..errors import ApiError, NotFound
from ..extensions import db, limiter
from ..models import Resume, ResumeVersion
from ..security import current_user, get_owned, login_required
from ..services import resume_service, storage
from .common import body, pagination, paginate, user_or_ip
from .schemas import ResumeRenameIn

bp = Blueprint("resumes", __name__, url_prefix="/api/resumes")


def _version(version_id, user):
    v = db.session.get(ResumeVersion, version_id)
    if v is None or v.resume.user_id != user.id:
        raise NotFound("Resume version")
    return v


@bp.get("")
@login_required
def list_resumes():
    user = current_user()
    page, per_page = pagination(default=20)
    q = Resume.query.filter_by(user_id=user.id).order_by(Resume.is_primary.desc(), Resume.updated_at.desc())
    return jsonify(paginate(q, page, per_page, lambda r: r.to_dict()))


@bp.post("")
@login_required
@limiter.limit("20 per hour", key_func=user_or_ip)
def upload():
    user = current_user()
    resume, version = resume_service.upload_resume(
        user, request.files.get("resume"), name=request.form.get("name"),
        max_resumes=current_app.config["MAX_RESUMES_PER_USER"])
    db.session.commit()
    return jsonify({"resume": resume.to_dict(), "version": version.to_dict(include_parsed=True)}), 201


@bp.post("/<int:resume_id>/versions")
@login_required
@limiter.limit("20 per hour", key_func=user_or_ip)
def upload_version(resume_id):
    user = current_user()
    get_owned(Resume, resume_id, user, "Resume")
    resume, version = resume_service.upload_resume(user, request.files.get("resume"), resume_id=resume_id)
    db.session.commit()
    return jsonify({"resume": resume.to_dict(), "version": version.to_dict(include_parsed=True)}), 201


@bp.get("/<int:resume_id>")
@login_required
def get_resume(resume_id):
    resume = get_owned(Resume, resume_id, current_user(), "Resume")
    return jsonify({**resume.to_dict(), "versions": [v.to_dict() for v in reversed(resume.versions)]})


@bp.patch("/<int:resume_id>")
@login_required
def rename(resume_id):
    resume = get_owned(Resume, resume_id, current_user(), "Resume")
    resume.name = body(ResumeRenameIn).name
    db.session.commit()
    return jsonify(resume.to_dict())


@bp.post("/<int:resume_id>/primary")
@login_required
def make_primary(resume_id):
    user = current_user()
    resume = get_owned(Resume, resume_id, user, "Resume")
    resume_service.set_primary(user.id, resume)
    db.session.commit()
    return jsonify(resume.to_dict())


@bp.delete("/<int:resume_id>")
@login_required
def delete(resume_id):
    user = current_user()
    resume = get_owned(Resume, resume_id, user, "Resume")
    resume_service.delete_resume(user.id, resume)
    db.session.commit()
    return "", 204


@bp.get("/versions/<int:version_id>")
@login_required
def get_version(version_id):
    v = _version(version_id, current_user())
    return jsonify({**v.to_dict(include_parsed=True), "resume_name": v.resume.name})


@bp.delete("/versions/<int:version_id>")
@login_required
def delete_version(version_id):
    user = current_user()
    v = _version(version_id, user)
    resume = v.resume
    if len(resume.versions) == 1:
        raise ApiError("This is the only version. Delete the resume instead.", status=400, code="last_version")
    stored = v.stored_filename
    db.session.delete(v)
    db.session.commit()
    storage.delete_file(stored)
    return "", 204


@bp.get("/versions/<int:version_id>/download")
@login_required
def download(version_id):
    v = _version(version_id, current_user())
    response = send_file(storage.path_for(v.stored_filename), mimetype=v.mime_type, as_attachment=True,
                         download_name=v.original_filename)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.get("/compare")
@login_required
def compare():
    user = current_user()
    try:
        a = _version(int(request.args["from"]), user)
        b = _version(int(request.args["to"]), user)
    except (KeyError, ValueError) as exc:
        raise ApiError("Provide ?from=<version_id>&to=<version_id>.", status=400) from exc
    if a.created_at > b.created_at:
        a, b = b, a
    return jsonify(resume_service.compare_versions(a, b))
