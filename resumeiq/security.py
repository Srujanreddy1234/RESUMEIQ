"""Password hashing, input validators and authorization helpers."""
import re
from functools import wraps

import bcrypt
from email_validator import EmailNotValidError, validate_email
from flask import g, request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from .errors import Forbidden, Unauthorized
from .extensions import db

BCRYPT_ROUNDS = 12
PASSWORD_MAX = 128  # bcrypt only uses the first 72 bytes; cap to avoid DoS.


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except ValueError:
        return False


# A pre-computed hash used to equalise timing when the email does not exist.
DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()

COMMON_PASSWORDS = {"password", "password1", "password123", "12345678", "123456789", "qwerty123", "iloveyou",
                    "admin123", "welcome1", "letmein1", "abc12345", "football1", "monkey123"}


def password_problems(password: str, min_length=8):
    problems = []
    if len(password) < min_length:
        problems.append(f"Password must be at least {min_length} characters.")
    if len(password) > PASSWORD_MAX:
        problems.append(f"Password must be at most {PASSWORD_MAX} characters.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        problems.append("Password must contain at least one letter and one number.")
    if password.lower() in COMMON_PASSWORDS:
        problems.append("This password is too common.")
    return problems


def password_strength(password: str) -> int:
    """0..4 score mirrored by the frontend strength meter."""
    score = 0
    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    if re.search(r"[a-z]", password) and re.search(r"[A-Z]", password):
        score += 1
    if re.search(r"\d", password) and re.search(r"[^A-Za-z0-9]", password):
        score += 1
    return min(score, 4)


def normalize_email(email: str) -> str:
    try:
        result = validate_email(email.strip(), check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    return result.normalized.lower()


def current_user():
    """Return the authenticated, active user or raise 401."""
    from .models import User
    cached = request.environ.get("riq.current_user")  # cache per request, never across requests
    if cached is not None:
        return cached
    verify_jwt_in_request()
    user_id = get_jwt_identity()
    user = db.session.get(User, int(user_id)) if user_id else None
    if not user or not user.is_active:
        raise Unauthorized("Your session is no longer valid. Please sign in again.")
    if get_jwt().get("tv") != user.token_version:
        raise Unauthorized("Your session has expired. Please sign in again.", code="session_expired")
    request.environ["riq.current_user"] = user
    g.user_id = user.id
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        current_user()
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user.is_admin:
            raise Forbidden("Administrator access is required.")
        return fn(*args, **kwargs)
    return wrapper


def get_owned(model, object_id, user, what=None):
    """Fetch a row by id that belongs to `user`, else 404 (never leak existence)."""
    from .errors import NotFound
    obj = db.session.get(model, object_id)
    owner_id = getattr(obj, "user_id", None)
    if obj is None or owner_id != user.id:
        raise NotFound(what or model.__name__.replace("_", " "))
    return obj


SAFE_URL_RE = re.compile(r"^https?://[^\s<>\"']+$", re.I)


def safe_url(value):
    """Allow only http(s) URLs — blocks javascript: and data: URLs in stored links."""
    if not value:
        return None
    value = value.strip()
    if not SAFE_URL_RE.match(value):
        raise ValueError("URL must start with http:// or https://")
    return value[:1000]
