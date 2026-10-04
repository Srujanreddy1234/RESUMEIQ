"""Application configuration.

Every secret comes from the environment. Nothing sensitive has a hard-coded
fallback: in production the app refuses to start without SECRET_KEY,
JWT_SECRET and DATABASE_URL.
"""
import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _database_url():
    url = os.getenv("DATABASE_URL", "")
    # Heroku/Railway style URLs use the deprecated "postgres://" scheme.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    ENV_NAME = "base"

    SECRET_KEY = os.getenv("SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET")

    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # ── Auth ──────────────────────────────────────────────────────────────
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=_int("JWT_ACCESS_MINUTES", 15))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=_int("JWT_REFRESH_DAYS", 30))
    JWT_COOKIE_SECURE = _bool("COOKIE_SECURE", True)
    JWT_COOKIE_SAMESITE = "Lax"
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_REFRESH_COOKIE_PATH = "/"
    JWT_ACCESS_COOKIE_NAME = "access_token"
    JWT_REFRESH_COOKIE_NAME = "refresh_token"
    JWT_SESSION_COOKIE = True  # browser-session cookies unless "remember me" sets an explicit max-age
    REMEMBER_ME_DAYS = _int("REMEMBER_ME_DAYS", 30)
    SHORT_SESSION_HOURS = _int("SHORT_SESSION_HOURS", 12)
    PASSWORD_MIN_LENGTH = 8
    LOGIN_MAX_FAILURES = _int("LOGIN_MAX_FAILURES", 5)
    LOGIN_LOCKOUT_MINUTES = _int("LOGIN_LOCKOUT_MINUTES", 15)
    PASSWORD_RESET_MINUTES = _int("PASSWORD_RESET_MINUTES", 30)

    # ── Rate limiting ─────────────────────────────────────────────────────
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "300 per minute")
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_ENABLED = True

    # ── CORS ──────────────────────────────────────────────────────────────
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

    # ── Files ─────────────────────────────────────────────────────────────
    # Uploads live outside the package and outside any static directory.
    STORAGE_DIR = os.getenv("STORAGE_DIR", os.path.join(BASE_DIR, "instance", "uploads"))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    MAX_RESUME_BYTES = 16 * 1024 * 1024
    MAX_AVATAR_BYTES = 2 * 1024 * 1024
    MAX_RESUMES_PER_USER = _int("MAX_RESUMES_PER_USER", 20)

    # ── AI ────────────────────────────────────────────────────────────────
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    AI_TIMEOUT_SECONDS = _int("AI_TIMEOUT_SECONDS", 60)
    AI_MAX_RETRIES = _int("AI_MAX_RETRIES", 2)
    AI_DAILY_REQUEST_LIMIT = _int("AI_DAILY_REQUEST_LIMIT", 60)
    AI_DAILY_TOKEN_LIMIT = _int("AI_DAILY_TOKEN_LIMIT", 400_000)

    # ── Jobs ──────────────────────────────────────────────────────────────
    ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
    ADZUNA_COUNTRY = os.getenv("ADZUNA_COUNTRY", "us")
    JOB_PROVIDERS = [p.strip() for p in os.getenv("JOB_PROVIDERS", "remotive,arbeitnow,adzuna").split(",") if p.strip()]
    JOB_CACHE_HOURS = _int("JOB_CACHE_HOURS", 6)
    JOB_HTTP_TIMEOUT = _int("JOB_HTTP_TIMEOUT", 15)

    # ── Background tasks ─────────────────────────────────────────────────
    TASKS_EAGER = _bool("TASKS_EAGER", False)
    TASK_WORKERS = _int("TASK_WORKERS", 4)

    # ── Email (password reset) ───────────────────────────────────────────
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = _int("SMTP_PORT", 587)
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@resumeiq.local")
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_JSON = _bool("LOG_JSON", True)
    TRUST_PROXY = _bool("TRUST_PROXY", False)

    @classmethod
    def validate(cls):
        pass


class DevelopmentConfig(Config):
    ENV_NAME = "development"
    DEBUG = True
    JWT_COOKIE_SECURE = _bool("COOKIE_SECURE", False)
    LOG_JSON = _bool("LOG_JSON", False)
    SQLALCHEMY_DATABASE_URI = _database_url() or "postgresql://localhost/resumeiq"
    # Development-only fallbacks so a fresh clone runs. Production refuses these.
    SECRET_KEY = os.getenv("SECRET_KEY") or "dev-only-secret-change-me"
    JWT_SECRET_KEY = os.getenv("JWT_SECRET") or "dev-only-jwt-secret-change-me"


class TestingConfig(Config):
    ENV_NAME = "testing"
    TESTING = True
    SECRET_KEY = "test-secret"
    JWT_SECRET_KEY = "test-jwt-secret-that-is-long-enough-for-hs256"
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    JWT_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False
    TASKS_EAGER = True
    GEMINI_API_KEY = ""
    JOB_PROVIDERS = []
    LOG_JSON = False
    LOG_LEVEL = "WARNING"


class ProductionConfig(Config):
    ENV_NAME = "production"
    DEBUG = False

    @classmethod
    def validate(cls):
        missing = [name for name, value in {
            "SECRET_KEY": cls.SECRET_KEY,
            "JWT_SECRET": cls.JWT_SECRET_KEY,
            "DATABASE_URL": cls.SQLALCHEMY_DATABASE_URI,
        }.items() if not value]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
        if len(cls.JWT_SECRET_KEY) < 32 or len(cls.SECRET_KEY) < 32:
            raise RuntimeError("SECRET_KEY and JWT_SECRET must be at least 32 characters in production.")


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name=None):
    name = name or os.getenv("APP_ENV", "development")
    return CONFIGS.get(name, DevelopmentConfig)
