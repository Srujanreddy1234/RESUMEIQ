"""Uniform API errors.

Every error response has the shape
    {"error": {"code": "...", "message": "...", "details": ..., "request_id": "..."}}
Stack traces and internal messages are never sent to the client.
"""
import logging

from flask import g, jsonify, redirect, request, url_for
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

log = logging.getLogger(__name__)


class ApiError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message, status=None, code=None, details=None):
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status
        if code is not None:
            self.code = code
        self.details = details


class NotFound(ApiError):
    status, code = 404, "not_found"

    def __init__(self, what="Resource"):
        super().__init__(f"{what} not found.")


class Forbidden(ApiError):
    status, code = 403, "forbidden"


class Unauthorized(ApiError):
    status, code = 401, "unauthorized"


class Conflict(ApiError):
    status, code = 409, "conflict"


class ValidationFailed(ApiError):
    status, code = 422, "validation_error"


class ServiceUnavailable(ApiError):
    status, code = 503, "service_unavailable"


def pydantic_details(exc: ValidationError):
    details = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
        msg = err.get("msg", "Invalid value")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        details.append({"field": field, "message": msg})
    return details


def _payload(code, message, details=None):
    body = {"code": code, "message": message, "request_id": getattr(g, "request_id", None)}
    if details is not None:
        body["details"] = details
    return {"error": body}


def _wants_json():
    if request.path.startswith("/api/") or request.path.startswith("/health"):
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json"


def register_error_handlers(app):
    from .services.observability import record_event

    @app.errorhandler(ApiError)
    def handle_api_error(exc):
        return jsonify(_payload(exc.code, exc.message, exc.details)), exc.status

    @app.errorhandler(ValidationError)
    def handle_validation(exc):
        return jsonify(_payload("validation_error", "Some fields are invalid.", pydantic_details(exc))), 422

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_exc):
        return jsonify(_payload("file_too_large", "File is too large. The maximum size is 16 MB.")), 413

    @app.errorhandler(429)
    def handle_rate_limit(exc):
        return jsonify(_payload("rate_limited", "Too many requests. Please wait a moment and try again.",
                                {"limit": str(getattr(exc, "description", ""))})), 429

    @app.errorhandler(HTTPException)
    def handle_http(exc):
        if exc.code == 401 and not _wants_json():
            return redirect(url_for("web.login"))
        if not _wants_json():
            from flask import render_template
            return render_template("error.html", code=exc.code, message=exc.description), exc.code
        return jsonify(_payload(exc.name.lower().replace(" ", "_"), exc.description)), exc.code

    @app.errorhandler(OperationalError)
    def handle_db_down(exc):
        log.error("database_unavailable", extra={"error_type": type(exc).__name__})
        return jsonify(_payload("database_unavailable",
                                "The database is temporarily unavailable. Please try again shortly.")), 503

    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(exc):
        from .extensions import db
        db.session.rollback()
        log.exception("database_error")
        record_event("db_error", type(exc).__name__, level="error")
        return jsonify(_payload("database_error", "A database error occurred.")), 500

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        log.exception("unhandled_exception")
        try:
            from .extensions import db
            db.session.rollback()
            record_event("error", type(exc).__name__, level="error")
        except Exception:  # pragma: no cover - never let error handling fail
            pass
        if not _wants_json():
            from flask import render_template
            return render_template("error.html", code=500, message="Something went wrong."), 500
        return jsonify(_payload("internal_error", "Something went wrong. Please try again.")), 500
