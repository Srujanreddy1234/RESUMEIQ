"""Structured logging, request tracing and operational event recording.

Never logs request bodies, passwords, tokens, API keys or resume content.
"""
import json
import logging
import re
import threading
import time
import uuid
from collections import defaultdict, deque

from flask import g, has_request_context, request

SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),                    # Google API keys
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)(['\"]?\s*[:=]\s*)([^\s,'\"&]+)"),
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWTs
]


def scrub(text):
    if not isinstance(text, str):
        return text
    text = SECRET_PATTERNS[0].sub("[REDACTED_KEY]", text)
    text = SECRET_PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    text = SECRET_PATTERNS[2].sub("[REDACTED_JWT]", text)
    return text


class ScrubFilter(logging.Filter):
    def filter(self, record):
        # Format first, then scrub the complete message (secrets may span the format string and its args).
        try:
            message = record.getMessage()
        except Exception:  # malformed format args - fall back to the raw template
            message = str(record.msg)
        record.msg = scrub(message)
        record.args = ()
        if has_request_context():
            record.request_id = getattr(g, "request_id", None)
        return True


class JsonFormatter(logging.Formatter):
    RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {"message", "asctime"}

    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = scrub(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(app):
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    if app.config.get("LOG_JSON"):
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(ScrubFilter())
    root.addHandler(handler)
    root.setLevel(app.config.get("LOG_LEVEL", "INFO"))
    for noisy in ("urllib3", "pdfminer", "werkzeug"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ── In-process latency metrics (per worker) ──────────────────────────────
_metrics_lock = threading.Lock()
_latencies = defaultdict(lambda: deque(maxlen=500))
_status_counts = defaultdict(int)


def latency_snapshot():
    with _metrics_lock:
        out = []
        for endpoint, values in _latencies.items():
            ordered = sorted(values)
            if not ordered:
                continue
            out.append({
                "endpoint": endpoint,
                "count": len(ordered),
                "p50_ms": ordered[len(ordered) // 2],
                "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
                "max_ms": ordered[-1],
            })
        return {"endpoints": sorted(out, key=lambda r: -r["p95_ms"])[:25], "status_counts": dict(_status_counts)}


def init_request_tracing(app):
    access_log = logging.getLogger("resumeiq.access")

    @app.before_request
    def _start():
        g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        if not re.fullmatch(r"[A-Za-z0-9\-]{8,64}", g.request_id):
            g.request_id = str(uuid.uuid4())
        g.request_started = time.perf_counter()

    @app.after_request
    def _finish(response):
        started = getattr(g, "request_started", None)
        if started is None:
            return response
        latency = int((time.perf_counter() - started) * 1000)
        response.headers["X-Request-ID"] = g.request_id
        if request.endpoint and request.endpoint != "static":
            with _metrics_lock:
                _latencies[request.endpoint].append(latency)
                _status_counts[f"{response.status_code // 100}xx"] += 1
            access_log.info("request", extra={
                "method": request.method, "path": request.path, "status": response.status_code,
                "latency_ms": latency, "user_id": getattr(g, "user_id", None),
            })
        return response


def insert_independent(model_cls, /, **values):
    """Insert a row outside the request transaction (survives rollbacks). Must never raise."""
    from ..extensions import db
    try:
        if db.engine.dialect.name == "sqlite":
            db.session.add(model_cls(**values))
            db.session.flush()
            return
        with db.engine.begin() as conn:
            conn.execute(model_cls.__table__.insert().values(**values))
    except Exception:  # pragma: no cover
        logging.getLogger(__name__).warning("independent insert failed for %s", model_cls.__tablename__)


def record_event(category, message, level="info", path=None):
    """Persist an operational event for the admin dashboard. Must never raise."""
    from ..extensions import db
    from ..models import SystemEvent, utcnow
    try:
        event = SystemEvent(
            category=category, level=level, message=scrub(str(message))[:255],
            path=(path or (request.path if has_request_context() else None)),
            request_id=getattr(g, "request_id", None) if has_request_context() else None,
            created_at=utcnow(),
        )
        if db.engine.dialect.name == "sqlite":  # tests: single shared in-memory connection
            db.session.add(event)
            db.session.flush()
            return
        # Separate connection so the event survives even if the request transaction rolls back.
        with db.engine.begin() as conn:
            conn.execute(SystemEvent.__table__.insert().values(
                category=event.category, level=event.level, message=event.message, path=event.path,
                request_id=event.request_id, created_at=event.created_at))
    except Exception:  # pragma: no cover
        logging.getLogger(__name__).warning("could not record system event", exc_info=False)
