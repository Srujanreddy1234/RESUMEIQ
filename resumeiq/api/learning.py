"""/api/skills (catalog, gap, graph, detail), /api/roadmap, /api/learning."""
from flask import Blueprint, jsonify, request

from ..errors import NotFound, ValidationFailed
from ..extensions import db, limiter
from ..models import LearningProgress, LearningResource, Roadmap, RoadmapItem, Skill, UserProject, UserSkill
from ..security import current_user, login_required
from ..services import roadmap as roadmap_service
from ..services.skill_extraction import canonical_skill
from ..services.skill_gap import compute_skill_gap, skill_detail
from .common import body, pagination, paginate, user_or_ip
from .schemas import ItemStatusIn, ProgressIn, ProjectDoneIn, RoadmapIn

skills_bp = Blueprint("skills", __name__, url_prefix="/api/skills")
roadmap_bp = Blueprint("roadmap", __name__, url_prefix="/api/roadmap")
learning_bp = Blueprint("learning", __name__, url_prefix="/api/learning")


def _role(user):
    role = (request.args.get("role") or (user.profile.target_career if user.profile else "") or "").strip()[:120]
    if not role:
        raise ValidationFailed("Set a target career in your profile or pass ?role=.", details=[{"field": "role", "message": "Required"}])
    return role


@skills_bp.get("")
@login_required
def catalog():
    page, per_page = pagination(default=50, maximum=200)
    q = Skill.query
    if request.args.get("q"):
        q = q.filter(Skill.name.ilike(f"%{request.args['q'][:60]}%"))
    if request.args.get("category"):
        q = q.filter(Skill.category == request.args["category"])
    return jsonify(paginate(q.order_by(Skill.name), page, per_page, lambda s: s.to_dict()))


@skills_bp.get("/gap")
@login_required
def gap():
    user = current_user()
    result = compute_skill_gap(user.id, _role(user))
    db.session.commit()
    return jsonify(result)


@skills_bp.get("/graph")
@login_required
def graph():
    """Current skills -> target skills -> missing -> learning path -> readiness."""
    user = current_user()
    role = _role(user)
    result = compute_skill_gap(user.id, role, persist=False)  # read-only: /gap owns persistence (avoids races)
    current = sorted(({"skill": us.skill.name, "level": us.level, "category": us.skill.category}
                      for us in UserSkill.query.filter_by(user_id=user.id)), key=lambda s: (-s["level"], s["skill"]))
    rm = roadmap_service.active_roadmap(user.id)
    path = []
    if rm and rm.target_role.lower() == role.lower():
        path = [{"skill": i.skill.name, "phase": i.phase, "status": i.status} for i in rm.items]
    else:
        path = [{"skill": i["skill"], "phase": n + 1, "status": "not_started"}
                for n, i in enumerate([i for i in result["items"] if i["status"] != "strong"][:8])]
    db.session.commit()
    return jsonify({
        "target_role": role, "role_profile": result["role_profile"], "current": current,
        "target": [{"skill": i["skill"], "importance": i["importance"], "required_level": i["required_level"],
                    "status": i["status"]} for i in result["items"]],
        "missing": [i for i in result["items"] if i["status"] != "strong"],
        "learning_path": path, "readiness": result["readiness"], "data_note": result["data_note"],
        "roadmap_exists": bool(path and rm),
    })


@skills_bp.get("/detail")
@login_required
def detail():
    user = current_user()
    name = canonical_skill(request.args.get("name", "")) or request.args.get("name", "").strip()
    data = skill_detail(user.id, name, request.args.get("role") or (user.profile.target_career if user.profile else None))
    if data is None:
        raise NotFound("Skill")
    return jsonify(data)


# ── Roadmap ─────────────────────────────────────────────────────────────
@roadmap_bp.post("")
@login_required
@limiter.limit("10 per minute", key_func=user_or_ip)
def generate():
    user = current_user()
    data = body(RoadmapIn)
    weekly = data.weekly_hours or (user.profile.weekly_study_hours if user.profile else 8)
    rm, note = roadmap_service.generate_roadmap(user.id, data.target_role, weekly)
    db.session.commit()
    return jsonify({**roadmap_service.roadmap_view(user.id, rm), "ai_note": note}), 201


@roadmap_bp.get("")
@login_required
def get_active():
    user = current_user()
    rm = roadmap_service.active_roadmap(user.id)
    if rm is None:
        return jsonify({"roadmap": None})
    return jsonify({"roadmap": roadmap_service.roadmap_view(user.id, rm)})


@roadmap_bp.patch("/items/<int:item_id>")
@login_required
def update_item(item_id):
    user = current_user()
    item = db.session.get(RoadmapItem, item_id)
    if item is None or db.session.get(Roadmap, item.roadmap_id).user_id != user.id:
        raise NotFound("Roadmap item")
    roadmap_service.set_item_status(user.id, item, body(ItemStatusIn).status)
    db.session.commit()
    return jsonify(roadmap_service.roadmap_view(user.id, db.session.get(Roadmap, item.roadmap_id)))


@roadmap_bp.get("/projects")
@login_required
@limiter.limit("10 per minute", key_func=user_or_ip)
def projects():
    user = current_user()
    return jsonify(roadmap_service.recommend_projects(user.id, _role(user)))


# ── Learning tracker ────────────────────────────────────────────────────
@learning_bp.get("/resources")
@login_required
def resources():
    page, per_page = pagination(default=30, maximum=100)
    q = LearningResource.query.join(Skill)
    if request.args.get("skill"):
        q = q.filter(Skill.name == (canonical_skill(request.args["skill"]) or request.args["skill"]))
    if request.args.get("type"):
        q = q.filter(LearningResource.resource_type == request.args["type"])
    if request.args.get("difficulty"):
        q = q.filter(LearningResource.difficulty == request.args["difficulty"])
    if request.args.get("q"):
        q = q.filter(LearningResource.title.ilike(f"%{request.args['q'][:60]}%"))
    if request.args.get("include_search") != "1":
        q = q.filter(LearningResource.is_search_link.is_(False))
    q = q.order_by(Skill.name, LearningResource.difficulty)
    return jsonify(paginate(q, page, per_page, lambda r: r.to_dict()))


@learning_bp.put("/progress/<int:resource_id>")
@login_required
def set_progress(resource_id):
    user = current_user()
    resource = db.session.get(LearningResource, resource_id)
    if resource is None:
        raise NotFound("Resource")
    data = body(ProgressIn)
    p = roadmap_service.set_resource_progress(user.id, resource, data.status, data.hours_spent)
    db.session.commit()
    return jsonify(p.to_dict())


@learning_bp.get("/progress")
@login_required
def list_progress():
    user = current_user()
    page, per_page = pagination(default=50)
    q = LearningProgress.query.filter_by(user_id=user.id).order_by(LearningProgress.updated_at.desc())
    if request.args.get("status"):
        q = q.filter(LearningProgress.status == request.args["status"])
    return jsonify(paginate(q, page, per_page, lambda p: p.to_dict()))


@learning_bp.get("/stats")
@login_required
def stats():
    return jsonify(roadmap_service.learning_stats(current_user().id))


@learning_bp.post("/projects")
@login_required
def complete_project():
    """Record a completed roadmap project; it also appears in the career profile."""
    user = current_user()
    data = body(ProjectDoneIn)
    techs = [canonical_skill(t) or t for t in data.technologies]
    p = UserProject(user_id=user.id, name=data.title, technologies=techs, url=data.url,
                    description="Completed from the learning roadmap.", source="roadmap")
    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201
