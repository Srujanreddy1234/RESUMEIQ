from ..extensions import db
from .base import TimestampMixin, iso


class Notification(TimestampMixin, db.Model):
    __tablename__ = "notifications"
    __table_args__ = (db.UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
                      db.Index("ix_notifications_user_read", "user_id", "is_read"))

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = db.Column(db.String(30), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    link = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    dedupe_key = db.Column(db.String(120))

    def to_dict(self):
        return {"id": self.id, "type": self.type, "title": self.title, "body": self.body, "link": self.link,
                "is_read": self.is_read, "created_at": iso(self.created_at)}


class AIUsageLog(db.Model):
    __tablename__ = "ai_usage_logs"
    __table_args__ = (db.Index("ix_ai_usage_logs_user_created", "user_id", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    service = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(60), nullable=False)
    prompt_tokens = db.Column(db.Integer, nullable=False, default=0)
    output_tokens = db.Column(db.Integer, nullable=False, default=0)
    latency_ms = db.Column(db.Integer, nullable=False, default=0)
    attempts = db.Column(db.Integer, nullable=False, default=1)
    success = db.Column(db.Boolean, nullable=False)
    error_type = db.Column(db.String(60))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)


class BackgroundTask(TimestampMixin, db.Model):
    """Long-running AI work. Stages are updated by the worker as each one really finishes."""
    __tablename__ = "background_tasks"

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="queued")  # queued|running|succeeded|failed
    stages = db.Column(db.JSON, nullable=False, default=list)
    result = db.Column(db.JSON)
    error_code = db.Column(db.String(60))
    error_message = db.Column(db.String(255))

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "status": self.status, "stages": self.stages,
                "result": self.result, "error": ({"code": self.error_code, "message": self.error_message}
                                                 if self.status == "failed" else None),
                "created_at": iso(self.created_at), "updated_at": iso(self.updated_at)}


class SystemEvent(db.Model):
    """Operational events (errors, AI/API failures, auth failures). Never contains user content."""
    __tablename__ = "system_events"
    __table_args__ = (db.Index("ix_system_events_category_created", "category", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(30), nullable=False)
    level = db.Column(db.String(10), nullable=False, default="info")
    message = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(255))
    request_id = db.Column(db.String(36))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)

    def to_dict(self):
        return {"id": self.id, "category": self.category, "level": self.level, "message": self.message,
                "path": self.path, "request_id": self.request_id, "created_at": iso(self.created_at)}
