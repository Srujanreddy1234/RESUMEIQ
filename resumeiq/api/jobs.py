"""/api/jobs (search, detail, save), /api/matches, /api/salary."""
from flask import Blueprint, jsonify, request

from ..errors import NotFound, ValidationFailed
from ..extensions import db, limiter
from ..models import Application, ApplicationEvent, Job, SavedJob
from ..security import current_user, login_required
from ..services import job_matching, job_sources, salary
from .common import body, int_arg, pagination, user_or_ip
from .schemas import SaveJobIn

bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")
matches_bp = Blueprint("matches", __name__, url_prefix="/api/matches")
salary_bp = Blueprint("salary", __name__, url_prefix="/api/salary")


def _filters():
    args = request.args
    work_types = [w for w in args.getlist("work_type") if w in ("remote", "hybrid", "onsite")]
    level = args.get("experience_level")
    if level and level not in ("entry", "mid", "senior"):
        raise ValidationFailed("experience_level must be entry, mid or senior.")
    return {
        "q": (args.get("q") or "").strip()[:100], "location": (args.get("location") or "").strip()[:100],
        "work_types": work_types, "salary_min": int_arg("salary_min", minimum=0), "experience_level": level,
        "company": (args.get("company") or "").strip()[:100],
        "skills": [s.strip()[:40] for s in (args.get("skills") or "").split(",") if s.strip()],
        "posted_within": int_arg("posted_within", minimum=1, maximum=365),
        "saved_only": args.get("saved") in ("1", "true"), "min_match": int_arg("min_match", minimum=0, maximum=100),
    }


@bp.get("")
@login_required
@limiter.limit("60 per minute", key_func=user_or_ip)
def search():
    user = current_user()
    f = _filters()
    page, per_page = pagination(default=12, maximum=50)
    sources = {}
    # Fetch fresh postings for explicit searches (cached per query to respect provider terms).
    query = f["q"] or (user.profile.target_career if user.profile and not f["saved_only"] else "")
    if query and page == 1 and not f["saved_only"]:
        sources = job_sources.refresh(query, f["location"] or None, force=request.args.get("refresh") == "1")
        if not f["q"]:
            f["q"] = query
    result = job_matching.search(user, f, page, per_page, sort=request.args.get("sort", "match"))
    db.session.commit()
    return jsonify({**result, "sources": sources, "query": f["q"],
                    "attribution": "Listings come from public job APIs (Remotive, Arbeitnow, Adzuna when configured). "
                                   "Click through to the original posting to apply."})


@bp.get("/<int:job_id>")
@login_required
def detail(job_id):
    user = current_user()
    job = db.session.get(Job, job_id)
    if job is None:
        raise NotFound("Job")
    ctx = job_matching.build_user_context(user)
    match = job_matching.get_matches(user, ctx, [job])[job.id]
    saved = SavedJob.query.filter_by(user_id=user.id, job_id=job.id).first()
    application = Application.query.filter_by(user_id=user.id, job_id=job.id).first()
    db.session.commit()
    return jsonify({**job.to_dict(include_description=True), "match": match.to_dict(), "saved": bool(saved),
                    "application_id": application.id if application else None})


@bp.post("/<int:job_id>/save")
@login_required
def save(job_id):
    user = current_user()
    if db.session.get(Job, job_id) is None:
        raise NotFound("Job")
    data = body(SaveJobIn)
    saved = SavedJob.query.filter_by(user_id=user.id, job_id=job_id).first()
    if saved is None:
        saved = SavedJob(user_id=user.id, job_id=job_id, notes=data.notes)
        db.session.add(saved)
    elif data.notes is not None:
        saved.notes = data.notes
    db.session.commit()
    return jsonify({"saved": True}), 201


@bp.delete("/<int:job_id>/save")
@login_required
def unsave(job_id):
    SavedJob.query.filter_by(user_id=current_user().id, job_id=job_id).delete()
    db.session.commit()
    return "", 204


@bp.post("/<int:job_id>/apply")
@login_required
def add_to_applications(job_id):
    """Create a tracker entry (stage: wishlist or applied) from a real job posting."""
    user = current_user()
    job = db.session.get(Job, job_id)
    if job is None:
        raise NotFound("Job")
    stage = (request.get_json(silent=True) or {}).get("stage", "wishlist")
    stage = stage if stage in ("wishlist", "applied") else "wishlist"
    app = Application.query.filter_by(user_id=user.id, job_id=job.id).first()
    if app is None:
        from datetime import date
        salary_text = job.salary_text or (f"{job.salary_currency or ''} {job.salary_min or ''}-{job.salary_max or ''}".strip()
                                          if job.salary_min or job.salary_max else None)
        app = Application(user_id=user.id, job_id=job.id, company=job.company or "Unknown company", position=job.title,
                          job_url=job.url, location=job.location, salary=salary_text, stage=stage,
                          date_applied=date.today() if stage == "applied" else None)
        db.session.add(app)
        db.session.flush()
        db.session.add(ApplicationEvent(application_id=app.id, from_stage=None, to_stage=stage))
    db.session.commit()
    return jsonify(app.to_dict()), 201


@matches_bp.get("")
@login_required
def top():
    user = current_user()
    limit = int_arg("limit", 10, 1, 50)
    items, strong = job_matching.top_matches(user, limit)
    db.session.commit()
    return jsonify({"items": items, "matched_60_plus": strong})


@matches_bp.get("/<int:job_id>")
@login_required
def explain(job_id):
    user = current_user()
    job = db.session.get(Job, job_id)
    if job is None:
        raise NotFound("Job")
    ctx = job_matching.build_user_context(user)
    result = job_matching.compute_match(ctx, job)
    return jsonify({"job": job.to_dict(), **result})


@salary_bp.get("")
@login_required
def salary_insights():
    user = current_user()
    role = (request.args.get("role") or (user.profile.target_career if user.profile else "") or "").strip()[:120]
    if not role:
        raise ValidationFailed("Provide a role (or set a target career in your profile).")
    level = request.args.get("experience_level") or None
    return jsonify(salary.insights(role, request.args.get("location") or None, level, request.args.get("company") or None))


@salary_bp.post("/interpret")
@login_required
@limiter.limit("10 per minute", key_func=user_or_ip)
def salary_interpret():
    user = current_user()
    payload = request.get_json(silent=True) or {}
    role = str(payload.get("role", ""))[:120]
    if not role:
        raise ValidationFailed("role is required.")
    data = salary.insights(role, payload.get("location") or None, payload.get("experience_level") or None,
                           payload.get("company") or None)
    return jsonify({"data": data, "interpretation": salary.interpret(user.id, data)})
