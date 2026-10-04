from ..extensions import db
from .base import TimestampMixin, iso

STAGES = ("wishlist", "applied", "assessment", "interview", "offer", "rejected")
STAGE_LABELS = {"wishlist": "Wishlist", "applied": "Applied", "assessment": "OA / Assessment",
                "interview": "Interview", "offer": "Offer", "rejected": "Rejected"}


class Application(TimestampMixin, db.Model):
    __tablename__ = "applications"
    __table_args__ = (db.Index("ix_applications_user_stage", "user_id", "stage"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="SET NULL"))
    company = db.Column(db.String(200), nullable=False)
    position = db.Column(db.String(200), nullable=False)
    job_url = db.Column(db.String(1000))
    salary = db.Column(db.String(80))
    location = db.Column(db.String(160))
    stage = db.Column(db.String(20), nullable=False, default="wishlist")
    board_position = db.Column(db.Integer, nullable=False, default=0)
    date_applied = db.Column(db.Date)
    interview_date = db.Column(db.DateTime(timezone=True))
    contact_person = db.Column(db.String(160))
    contact_email = db.Column(db.String(255))
    notes = db.Column(db.Text)

    events = db.relationship("ApplicationEvent", cascade="all, delete-orphan", passive_deletes=True,
                             order_by="ApplicationEvent.created_at")

    def to_dict(self):
        return {
            "id": self.id, "job_id": self.job_id, "company": self.company, "position": self.position,
            "job_url": self.job_url, "salary": self.salary, "location": self.location, "stage": self.stage,
            "stage_label": STAGE_LABELS.get(self.stage, self.stage), "board_position": self.board_position,
            "date_applied": self.date_applied.isoformat() if self.date_applied else None,
            "interview_date": iso(self.interview_date), "contact_person": self.contact_person,
            "contact_email": self.contact_email, "notes": self.notes,
            "created_at": iso(self.created_at), "updated_at": iso(self.updated_at),
        }


class ApplicationEvent(TimestampMixin, db.Model):
    """Stage history; powers response-rate and pipeline analytics."""
    __tablename__ = "application_events"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    from_stage = db.Column(db.String(20))
    to_stage = db.Column(db.String(20), nullable=False)


class CoverLetter(TimestampMixin, db.Model):
    __tablename__ = "cover_letters"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_version_id = db.Column(db.Integer, db.ForeignKey("resume_versions.id", ondelete="SET NULL"))
    job_description_id = db.Column(db.Integer, db.ForeignKey("job_descriptions.id", ondelete="SET NULL"))
    company = db.Column(db.String(200), nullable=False)
    position = db.Column(db.String(200), nullable=False)
    tone = db.Column(db.String(20), nullable=False, default="formal")
    content = db.Column(db.Text, nullable=False)
    ai_used = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {"id": self.id, "company": self.company, "position": self.position, "tone": self.tone,
                "content": self.content, "ai_used": self.ai_used, "resume_version_id": self.resume_version_id,
                "created_at": iso(self.created_at), "updated_at": iso(self.updated_at)}
