"""Authentication: register, login, refresh (rotating), logout, password reset/change.

Tokens are JWTs stored in HTTP-only, SameSite=Lax cookies with double-submit CSRF
protection. Refresh tokens rotate on every use; used/revoked JTIs are blocklisted.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (create_access_token, create_refresh_token, decode_token, get_jwt, get_jwt_identity,
                                jwt_required, set_access_cookies, set_refresh_cookies, unset_jwt_cookies)

from ..errors import ApiError, Conflict, Unauthorized, ValidationFailed
from ..extensions import db, limiter
from ..models import PasswordResetToken, Profile, TokenBlocklist, User, utcnow
from ..security import DUMMY_HASH, current_user, hash_password, login_required, password_problems, verify_password
from ..services.email import send_password_reset
from ..services.observability import record_event
from ..services.skill_extraction import seed_skills
from .common import body
from .schemas import ChangePasswordIn, ForgotIn, LoginIn, RegisterIn, ResetIn

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
log = logging.getLogger(__name__)


def _issue(response, user, remember):
    claims = {"tv": user.token_version, "rm": bool(remember)}
    access = create_access_token(identity=str(user.id), additional_claims=claims)
    refresh_expires = (timedelta(days=current_app.config["REMEMBER_ME_DAYS"]) if remember
                       else timedelta(hours=current_app.config["SHORT_SESSION_HOURS"]))
    refresh = create_refresh_token(identity=str(user.id), additional_claims=claims, expires_delta=refresh_expires)
    # Remember-me: persistent cookies; otherwise browser-session cookies (cleared when the browser closes).
    max_age = int(refresh_expires.total_seconds()) if remember else None
    set_access_cookies(response, access, max_age=max_age)
    set_refresh_cookies(response, refresh, max_age=max_age)
    return response


def _blocklist(jwt_payload):
    exp = datetime.fromtimestamp(jwt_payload["exp"], tz=timezone.utc)
    if not TokenBlocklist.query.filter_by(jti=jwt_payload["jti"]).first():
        db.session.add(TokenBlocklist(jti=jwt_payload["jti"], token_type=jwt_payload.get("type", "access"),
                                      user_id=int(jwt_payload["sub"]), expires_at=exp))


def _check_password(password, confirm):
    if password != confirm:
        raise ValidationFailed("Passwords do not match.", details=[{"field": "confirm_password", "message": "Passwords do not match."}])
    problems = password_problems(password, current_app.config["PASSWORD_MIN_LENGTH"])
    if problems:
        raise ValidationFailed(problems[0], details=[{"field": "password", "message": p} for p in problems])


@bp.post("/register")
@limiter.limit("5 per minute; 30 per hour")
def register():
    data = body(RegisterIn)
    _check_password(data.password, data.confirm_password)
    if User.query.filter_by(email=data.email).first():
        raise Conflict("An account with this email already exists.", code="email_taken")
    user = User(email=data.email, full_name=data.full_name, password_hash=hash_password(data.password))
    db.session.add(user)
    db.session.flush()
    db.session.add(Profile(user_id=user.id))
    seed_skills()
    db.session.commit()
    log.info("user_registered", extra={"user_id": user.id})
    return jsonify({"user": user.to_dict(), "message": "Account created. You can sign in now."}), 201


@bp.post("/login")
@limiter.limit("10 per minute; 60 per hour")
def login():
    data = body(LoginIn)
    email = (data.email or "").strip().lower()
    user = User.query.filter_by(email=email).first()
    now = utcnow()
    if user and user.locked_until and user.locked_until.replace(tzinfo=user.locked_until.tzinfo or timezone.utc) > now:
        record_event("auth_failure", "login while locked")
        raise ApiError("Too many failed attempts. Try again in a few minutes or reset your password.",
                       status=429, code="account_locked")
    if not user:
        verify_password(data.password, DUMMY_HASH)  # equalise timing
        record_event("auth_failure", "unknown email")
        raise Unauthorized("Invalid email or password.", code="invalid_credentials")
    if not verify_password(data.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= current_app.config["LOGIN_MAX_FAILURES"]:
            user.locked_until = now + timedelta(minutes=current_app.config["LOGIN_LOCKOUT_MINUTES"])
            user.failed_login_count = 0
        db.session.commit()
        record_event("auth_failure", "bad password")
        raise Unauthorized("Invalid email or password.", code="invalid_credentials")
    if not user.is_active:
        raise Unauthorized("This account has been deactivated.", code="account_inactive")
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.session.commit()
    return _issue(jsonify({"user": user.to_dict(), "redirect": "/dashboard"}), user, data.remember_me)


@bp.post("/refresh")
@limiter.limit("30 per minute")
@jwt_required(refresh=True)
def refresh():
    payload = get_jwt()
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or not user.is_active or payload.get("tv") != user.token_version:
        raise Unauthorized("Your session has expired. Please sign in again.", code="session_expired")
    _blocklist(payload)  # rotation: a refresh token is single-use
    db.session.commit()
    return _issue(jsonify({"user": user.to_dict()}), user, payload.get("rm", False))


@bp.post("/logout")
def logout():
    response = jsonify({"message": "Signed out."})
    # Revoke whichever tokens are present and still valid. (Forced logout is harmless, so no CSRF check.)
    for cookie in (current_app.config["JWT_ACCESS_COOKIE_NAME"], current_app.config["JWT_REFRESH_COOKIE_NAME"]):
        raw = request.cookies.get(cookie)
        if not raw:
            continue
        try:
            _blocklist(decode_token(raw))
        except Exception:
            pass
    db.session.commit()
    unset_jwt_cookies(response)
    return response


@bp.get("/me")
@login_required
def me():
    user = current_user()
    return jsonify({"user": user.to_dict(), "profile": user.profile.to_dict() if user.profile else None})


@bp.post("/forgot-password")
@limiter.limit("3 per minute; 10 per hour")
def forgot_password():
    data = body(ForgotIn)
    user = User.query.filter_by(email=(data.email or "").strip().lower()).first()
    if user and user.is_active:
        raw = secrets.token_urlsafe(32)
        db.session.add(PasswordResetToken(
            user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=utcnow() + timedelta(minutes=current_app.config["PASSWORD_RESET_MINUTES"])))
        db.session.commit()
        send_password_reset(user, raw)
    # Same response whether or not the account exists (no user enumeration).
    return jsonify({"message": "If an account exists for that email, a reset link has been sent."})


@bp.post("/reset-password")
@limiter.limit("5 per minute")
def reset_password():
    data = body(ResetIn)
    _check_password(data.password, data.confirm_password)
    token = PasswordResetToken.query.filter_by(token_hash=hashlib.sha256(data.token.encode()).hexdigest()).first()
    now = utcnow()
    if not token or token.used_at or token.expires_at.replace(tzinfo=token.expires_at.tzinfo or timezone.utc) < now:
        raise ApiError("This reset link is invalid or has expired. Request a new one.", status=400, code="invalid_token")
    user = db.session.get(User, token.user_id)
    user.password_hash = hash_password(data.password)
    user.token_version += 1  # signs out all existing sessions
    user.failed_login_count = 0
    user.locked_until = None
    token.used_at = now
    db.session.commit()
    return jsonify({"message": "Password updated. Please sign in."})


@bp.post("/change-password")
@login_required
@limiter.limit("5 per minute")
def change_password():
    data = body(ChangePasswordIn)
    user = current_user()
    if not verify_password(data.current_password, user.password_hash):
        raise ApiError("Current password is incorrect.", status=400, code="invalid_password")
    _check_password(data.new_password, data.confirm_password)
    user.password_hash = hash_password(data.new_password)
    user.token_version += 1
    db.session.commit()
    # Issue fresh tokens for this device; other sessions are invalidated.
    return _issue(jsonify({"message": "Password changed."}), user, get_jwt().get("rm", False))
