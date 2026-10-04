"""ResumeIQ - AI Career Intelligence Platform."""
import os

from flask import Flask, jsonify, request
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .config import get_config
from .extensions import cors, db, jwt, limiter, migrate

__version__ = "2.0.0"


def create_app(config_name=None):
    config = get_config(config_name)
    config.validate()
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config)
    app.config["RATELIMIT_DEFAULT"] = config.RATELIMIT_DEFAULT

    from .services.observability import configure_logging, init_request_tracing
    configure_logging(app)
    init_request_tracing(app)

    if app.config.get("TRUST_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations"))
    jwt.init_app(app)
    limiter.init_app(app)
    if app.config["CORS_ORIGINS"]:
        cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}}, supports_credentials=True)

    from . import models  # noqa: F401  (register tables)
    from .services.ai import GeminiClient
    app.extensions["ai_client"] = GeminiClient()

    _register_jwt_callbacks(app)
    _register_blueprints(app)
    from .errors import register_error_handlers
    register_error_handlers(app)
    _register_security_headers(app)
    _register_cli(app)

    @limiter.request_filter
    def _skip_static():
        return request.endpoint == "static" or request.path.startswith("/health")

    @app.context_processor
    def _inject():
        return {"app_version": __version__, "ai_configured": bool(app.config.get("GEMINI_API_KEY"))}

    os.makedirs(app.config["STORAGE_DIR"], mode=0o700, exist_ok=True)
    return app


@event.listens_for(Engine, "connect")
def _sqlite_fk(dbapi_connection, _record):
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _register_jwt_callbacks(app):
    from .models import TokenBlocklist

    @jwt.token_in_blocklist_loader
    def _revoked(_header, payload):
        return db.session.query(TokenBlocklist.id).filter_by(jti=payload["jti"]).first() is not None

    def _err(code, message):
        return jsonify({"error": {"code": code, "message": message}}), 401

    @jwt.expired_token_loader
    def _expired(_h, _p):
        return _err("token_expired", "Your session has expired.")

    @jwt.invalid_token_loader
    def _invalid(reason):
        return _err("invalid_token", "Your session is invalid. Please sign in again.")

    @jwt.unauthorized_loader
    def _missing(reason):
        if "CSRF" in (reason or ""):
            return _err("csrf_failed", "Security check failed. Refresh the page and try again.")
        return _err("unauthorized", "Please sign in to continue.")

    @jwt.revoked_token_loader
    def _revoked_cb(_h, _p):
        return _err("token_revoked", "Your session has ended. Please sign in again.")


def _register_blueprints(app):
    from .api.analysis import bp as analysis_bp, jd_bp, tasks_bp
    from .api.auth import bp as auth_bp
    from .api.career import apps_bp, cover_bp, interview_bp
    from .api.jobs import bp as jobs_bp, matches_bp, salary_bp
    from .api.learning import learning_bp, roadmap_bp, skills_bp
    from .api.profile import bp as profile_bp, users_bp
    from .api.resumes import bp as resumes_bp
    from .api.system import admin_bp, analytics_bp, docs_bp, health_bp, notifications_bp, search_bp
    from .web.routes import bp as web_bp
    for blueprint in (auth_bp, users_bp, profile_bp, resumes_bp, analysis_bp, jd_bp, tasks_bp, jobs_bp, matches_bp,
                      salary_bp, skills_bp, roadmap_bp, learning_bp, interview_bp, apps_bp, cover_bp, analytics_bp,
                      notifications_bp, search_bp, admin_bp, health_bp, docs_bp, web_bp):
        app.register_blueprint(blueprint)


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")


def _register_security_headers(app):
    @app.after_request
    def _headers(response):
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if app.config.get("JWT_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.path.startswith("/api/") and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response


def _register_cli(app):
    import click

    @app.cli.command("seed")
    def seed():
        """Seed the skill taxonomy and curated learning resources."""
        from .services.roadmap import seed_resources
        from .services.skill_extraction import seed_skills
        seed_skills()
        seed_resources()
        db.session.commit()
        click.echo("Seeded skills and learning resources.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", default="Administrator")
    @click.password_option()
    def create_admin(email, name, password):
        """Create (or promote) an administrator account."""
        from .models import Profile, User
        from .security import hash_password, normalize_email, password_problems
        email = normalize_email(email)
        problems = password_problems(password)
        if problems:
            raise click.ClickException(problems[0])
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(email=email, full_name=name, password_hash=hash_password(password), role="admin")
            db.session.add(user)
            db.session.flush()
            db.session.add(Profile(user_id=user.id))
        else:
            user.role = "admin"
        db.session.commit()
        click.echo(f"Admin ready: {email}")

    @app.cli.command("send-reminders")
    def send_reminders():
        """Generate interview / follow-up / saved-job reminders for all users (run from cron)."""
        from .models import User
        from .services.notifications import generate_reminders
        total = sum(generate_reminders(uid) for (uid,) in db.session.query(User.id).filter(User.is_active.is_(True)))
        db.session.commit()
        click.echo(f"Created {total} reminder(s).")

    @app.cli.command("cleanup")
    @click.option("--job-days", default=60, help="Delete unsaved, unapplied jobs older than this many days.")
    def cleanup(job_days):
        """Remove orphaned upload files, expired tokens and stale job postings."""
        from datetime import timedelta
        from .models import (Application, Job, PasswordResetToken, Profile, ResumeVersion, SavedJob, TokenBlocklist,
                             utcnow)
        from .services.storage import cleanup_orphans
        known = {v for (v,) in db.session.query(ResumeVersion.stored_filename)}
        known |= {a for (a,) in db.session.query(Profile.avatar_filename).filter(Profile.avatar_filename.isnot(None))}
        removed = cleanup_orphans(known)
        now = utcnow()
        tokens = TokenBlocklist.query.filter(TokenBlocklist.expires_at < now).delete()
        resets = PasswordResetToken.query.filter(PasswordResetToken.expires_at < now - timedelta(days=1)).delete()
        keep = db.session.query(SavedJob.job_id).union(db.session.query(Application.job_id).filter(Application.job_id.isnot(None)))
        jobs = (Job.query.filter(Job.fetched_at < now - timedelta(days=job_days), ~Job.id.in_(keep))
                .delete(synchronize_session=False))
        db.session.commit()
        click.echo(f"Removed {removed} orphan file(s), {tokens} expired token(s), {resets} reset token(s), {jobs} stale job(s).")

    @app.cli.command("fetch-jobs")
    @click.argument("query")
    @click.option("--location", default=None)
    def fetch_jobs(query, location):
        """Warm the job cache for a query from the configured providers."""
        from .services.job_sources import refresh
        click.echo(refresh(query, location, force=True))
