"""/api/analytics, /api/notifications, /api/search, /api/admin, /health, /api/docs."""
from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import text

from ..errors import NotFound
from ..extensions import db
from ..models import AnalysisHistory, Notification, Resume, User
from ..security import admin_required, current_user, get_owned, login_required
from ..services import analytics
from ..services.notifications import generate_reminders
from .common import body, pagination, paginate
from .schemas import AdminUserPatch

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")
notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")
search_bp = Blueprint("search", __name__, url_prefix="/api/search")
admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")
health_bp = Blueprint("health", __name__)
docs_bp = Blueprint("docs", __name__, url_prefix="/api")


@analytics_bp.get("/dashboard")
@login_required
def dashboard():
    data = analytics.dashboard(current_user())
    db.session.commit()  # cached job matches
    return jsonify(data)


@analytics_bp.get("/applications")
@login_required
def applications():
    return jsonify(analytics.application_analytics(current_user().id))


@analytics_bp.get("/insights")
@login_required
def insights():
    return jsonify({"insights": analytics.career_insights(current_user()),
                    "note": "Every insight is computed from data stored in your account; the evidence is shown with it."})


@analytics_bp.get("/charts")
@login_required
def charts():
    return jsonify(analytics.charts(current_user().id))


# ── Notifications ───────────────────────────────────────────────────────
@notifications_bp.get("")
@login_required
def list_notifications():
    user = current_user()
    generate_reminders(user.id)
    db.session.commit()
    page, per_page = pagination(default=20)
    q = Notification.query.filter_by(user_id=user.id)
    if request.args.get("unread") == "1":
        q = q.filter_by(is_read=False)
    q = q.order_by(Notification.created_at.desc())
    data = paginate(q, page, per_page, lambda n: n.to_dict())
    data["unread"] = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    return jsonify(data)


@notifications_bp.get("/unread-count")
@login_required
def unread_count():
    return jsonify({"unread": Notification.query.filter_by(user_id=current_user().id, is_read=False).count()})


@notifications_bp.post("/<int:nid>/read")
@login_required
def mark_read(nid):
    n = get_owned(Notification, nid, current_user(), "Notification")
    n.is_read = True
    db.session.commit()
    return jsonify(n.to_dict())


@notifications_bp.post("/read-all")
@login_required
def mark_all_read():
    count = Notification.query.filter_by(user_id=current_user().id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"updated": count})


@notifications_bp.delete("/<int:nid>")
@login_required
def delete_notification(nid):
    n = get_owned(Notification, nid, current_user(), "Notification")
    db.session.delete(n)
    db.session.commit()
    return "", 204


# ── Search ─────────────────────────────────────────────────────────────
@search_bp.get("")
@login_required
def search():
    q = (request.args.get("q") or "").strip()[:80]
    if len(q) < 2:
        return jsonify({"jobs": [], "skills": [], "resources": [], "applications": [], "analyses": []})
    return jsonify(analytics.global_search(current_user().id, q))


# ── Admin (aggregates only; no resume content) ─────────────────────────
@admin_bp.get("/overview")
@admin_required
def admin_overview():
    return jsonify(analytics.admin_overview())


@admin_bp.get("/users")
@admin_required
def admin_users():
    page, per_page = pagination(default=25)
    q = User.query.order_by(User.created_at.desc())
    if request.args.get("q"):
        q = q.filter(User.email.ilike(f"%{request.args['q'][:80]}%"))

    def ser(u):
        return {**u.to_dict(), "is_active": u.is_active,
                "resumes": Resume.query.filter_by(user_id=u.id).count(),
                "analyses": AnalysisHistory.query.filter_by(user_id=u.id).count()}
    return jsonify(paginate(q, page, per_page, ser))


@admin_bp.patch("/users/<int:user_id>")
@admin_required
def admin_update_user(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        raise NotFound("User")
    data = body(AdminUserPatch)
    if target.id == current_user().id and (data.is_active is False or data.role == "user"):
        from ..errors import ApiError
        raise ApiError("You can't deactivate or demote your own admin account.", status=400)
    if data.is_active is not None:
        target.is_active = data.is_active
        if not data.is_active:
            target.token_version += 1
    if data.role:
        target.role = data.role
    db.session.commit()
    return jsonify(target.to_dict())


# ── Health & docs ──────────────────────────────────────────────────────
@health_bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "healthy"})
    except Exception:
        return jsonify({"status": "unhealthy", "database": "unavailable"}), 503


@health_bp.get("/health/live")
def live():
    return jsonify({"status": "alive"})


@docs_bp.get("/docs")
def api_docs():
    """Machine-readable index of every API route (generated from the URL map)."""
    routes = []
    for rule in current_app.url_map.iter_rules():
        if not (rule.rule.startswith("/api/") or rule.rule.startswith("/health")):
            continue
        view = current_app.view_functions[rule.endpoint]
        doc = (view.__doc__ or "").strip().splitlines()[0] if view.__doc__ else None
        routes.append({"path": rule.rule, "methods": sorted(rule.methods - {"HEAD", "OPTIONS"}), "endpoint": rule.endpoint,
                       "summary": doc})
    routes.sort(key=lambda r: (r["path"], r["methods"]))
    return jsonify({"name": "ResumeIQ API", "version": "2.0", "auth": "JWT in HTTP-only cookies; send X-CSRF-TOKEN header "
                    "(value of csrf_access_token cookie) on POST/PUT/PATCH/DELETE.",
                    "errors": {"shape": {"error": {"code": "string", "message": "string", "details": "optional",
                                                   "request_id": "string"}}},
                    "routes": routes})
