"""Server-rendered page shells (data is loaded from the REST API by page modules) and print-friendly reports."""
from flask import Blueprint, abort, make_response, redirect, render_template, request, url_for
from flask_jwt_extended import create_access_token, decode_token, set_access_cookies, verify_jwt_in_request
from flask_jwt_extended import get_jwt, get_jwt_identity

from ..extensions import db
from ..models import AnalysisHistory, InterviewSession, TokenBlocklist, User, utcnow

bp = Blueprint("web", __name__)

NAV = [
    ("Overview", [("dashboard", "Dashboard", "grid"), ("resumes", "My Resumes", "file"),
                  ("analyzer", "Resume Analyzer", "scan"), ("improve", "Improve Resume", "wand")]),
    ("Jobs", [("job_matcher", "Job Matcher", "target"), ("jobs", "Jobs", "briefcase"),
              ("applications", "Applications", "kanban"), ("cover_letters", "Cover Letters", "mail"),
              ("salary", "Salary Insights", "coins")]),
    ("Growth", [("skill_gap", "Skill Gap", "graph"), ("roadmap", "Learning Roadmap", "map"),
                ("interview", "Interview Prep", "mic")]),
    ("You", [("profile", "Career Profile", "user"), ("analytics", "Analytics", "chart"),
             ("history", "Analysis History", "clock"), ("settings", "Settings", "gear")]),
]

PAGES = {
    "dashboard": ("/dashboard", "Dashboard"), "resumes": ("/resumes", "My Resumes"),
    "analyzer": ("/analyzer", "Resume Analyzer"), "improve": ("/improve", "Improve Resume"),
    "job_matcher": ("/job-matcher", "Job Matcher"), "jobs": ("/jobs", "Jobs"),
    "applications": ("/applications", "Applications"), "cover_letters": ("/cover-letters", "Cover Letters"),
    "salary": ("/salary", "Salary Insights"), "skill_gap": ("/skill-gap", "Skill Gap"),
    "roadmap": ("/roadmap", "Learning Roadmap"), "interview": ("/interview", "Interview Prep"),
    "profile": ("/profile", "Career Profile"), "analytics": ("/analytics", "Analytics"),
    "history": ("/history", "Analysis History"), "settings": ("/settings", "Settings"),
    "notifications": ("/notifications", "Notifications"), "admin": ("/admin", "Admin"),
}


def _page_user():
    """Return (user, fresh_access_token_or_None). Silently renews an expired access token from a valid refresh cookie."""
    try:
        verify_jwt_in_request(locations=["cookies"])
        user = db.session.get(User, int(get_jwt_identity()))
        if user and user.is_active and get_jwt().get("tv") == user.token_version:
            return user, None
    except Exception:
        pass
    raw = request.cookies.get("refresh_token")
    if not raw:
        return None, None
    try:
        payload = decode_token(raw)
    except Exception:
        return None, None
    if TokenBlocklist.query.filter_by(jti=payload["jti"]).first():
        return None, None
    user = db.session.get(User, int(payload["sub"]))
    if not user or not user.is_active or payload.get("tv") != user.token_version:
        return None, None
    token = create_access_token(identity=str(user.id), additional_claims={"tv": user.token_version, "rm": payload.get("rm", False)})
    return user, token


def _render_page(key, admin=False):
    user, token = _page_user()
    if user is None:
        return redirect(url_for("web.login", next=request.full_path.rstrip("?")))
    if admin and not user.is_admin:
        abort(403)
    template = f"pages/{key}.html"
    resp = make_response(render_template(template, user=user, nav=NAV, pages=PAGES, active=key, title=PAGES[key][1]))
    if token:
        set_access_cookies(resp, token)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _register_pages():
    for key, (path, _title) in PAGES.items():
        def view(key=key):
            return _render_page(key, admin=(key == "admin"))
        bp.add_url_rule(path, key, view, methods=["GET"])


_register_pages()


@bp.get("/")
def index():
    user, _ = _page_user()
    if user:
        return redirect(url_for("web.dashboard"))
    return render_template("landing.html")


def _auth_page(template):
    user, _ = _page_user()
    if user and template != "auth/reset.html":
        return redirect(url_for("web.dashboard"))
    return render_template(template)


@bp.get("/login")
def login():
    return _auth_page("auth/login.html")


@bp.get("/register")
def register():
    return _auth_page("auth/register.html")


@bp.get("/forgot-password")
def forgot_password():
    return _auth_page("auth/forgot.html")


@bp.get("/reset-password")
def reset_password():
    return _auth_page("auth/reset.html")


@bp.get("/privacy")
def privacy():
    return render_template("legal/privacy.html")


@bp.get("/terms")
def terms():
    return render_template("legal/terms.html")


# ── Print-friendly reports (Save as PDF from the browser) ───────────────
@bp.get("/reports/<kind>")
def report(kind):
    from ..services import analytics
    from ..services.roadmap import active_roadmap, learning_stats, roadmap_view
    from ..services.skill_gap import compute_skill_gap
    user, token = _page_user()
    if user is None:
        return redirect(url_for("web.login", next=request.full_path))
    ctx = {"user": user, "kind": kind, "now_str": utcnow().strftime("%d %b %Y %H:%M UTC")}
    target = user.profile.target_career if user.profile else None
    if kind == "analysis":
        a = db.session.get(AnalysisHistory, request.args.get("id", type=int) or 0)
        if a is None or a.user_id != user.id:
            abort(404)
        ctx["analysis"] = a.to_dict()
    elif kind == "career":
        ctx["dashboard"] = analytics.dashboard(user)
        ctx["insights"] = analytics.career_insights(user)
        ctx["learning"] = learning_stats(user.id)
        db.session.commit()
    elif kind == "skill-gap":
        role = request.args.get("role") or target
        if not role:
            abort(400)
        ctx["gap"] = compute_skill_gap(user.id, role, persist=False)
    elif kind == "roadmap":
        rm = active_roadmap(user.id)
        if rm is None:
            abort(404)
        ctx["roadmap"] = roadmap_view(user.id, rm)
    elif kind == "interview":
        s = db.session.get(InterviewSession, request.args.get("id", type=int) or 0)
        if s is None or s.user_id != user.id:
            abort(404)
        ctx["session"] = s.to_dict()
    elif kind == "applications":
        ctx["apps"] = analytics.application_analytics(user.id)
    else:
        abort(404)
    resp = make_response(render_template(f"reports/{kind}.html", **ctx))
    if token:
        set_access_cookies(resp, token)
    resp.headers["Cache-Control"] = "no-store"
    return resp
