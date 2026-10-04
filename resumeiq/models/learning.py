from ..extensions import db
from .base import TimestampMixin, iso


class LearningResource(TimestampMixin, db.Model):
    """Curated resource. URLs come only from the reviewed catalog in data/resources.json."""
    __tablename__ = "learning_resources"
    __table_args__ = (db.UniqueConstraint("skill_id", "url", name="uq_learning_resources_skill_url"),)

    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    platform = db.Column(db.String(80), nullable=False)
    resource_type = db.Column(db.String(30), nullable=False)  # documentation|course|youtube|book|certification|practice
    difficulty = db.Column(db.String(20), nullable=False, default="beginner")
    est_hours = db.Column(db.Integer)
    url = db.Column(db.String(500), nullable=False)
    is_search_link = db.Column(db.Boolean, nullable=False, default=False)
    is_free = db.Column(db.Boolean, nullable=False, default=True)

    skill = db.relationship("Skill")

    def to_dict(self):
        return {"id": self.id, "skill": self.skill.name, "skill_id": self.skill_id, "title": self.title,
                "platform": self.platform, "type": self.resource_type, "difficulty": self.difficulty,
                "est_hours": self.est_hours, "url": self.url, "is_search_link": self.is_search_link,
                "is_free": self.is_free}


class Roadmap(TimestampMixin, db.Model):
    __tablename__ = "roadmaps"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_role = db.Column(db.String(120), nullable=False)
    weekly_hours = db.Column(db.Integer, nullable=False, default=8)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    summary = db.Column(db.Text)

    items = db.relationship("RoadmapItem", cascade="all, delete-orphan", order_by="RoadmapItem.position",
                            passive_deletes=True)


class RoadmapItem(TimestampMixin, db.Model):
    __tablename__ = "roadmap_items"

    id = db.Column(db.Integer, primary_key=True)
    roadmap_id = db.Column(db.Integer, db.ForeignKey("roadmaps.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    phase = db.Column(db.Integer, nullable=False)
    position = db.Column(db.Integer, nullable=False)
    what_to_learn = db.Column(db.JSON, nullable=False, default=list)
    why = db.Column(db.Text)
    prerequisites = db.Column(db.JSON, nullable=False, default=list)
    project_ideas = db.Column(db.JSON, nullable=False, default=list)
    est_hours = db.Column(db.Integer, nullable=False, default=10)
    status = db.Column(db.String(20), nullable=False, default="not_started")

    skill = db.relationship("Skill")


class LearningProgress(TimestampMixin, db.Model):
    __tablename__ = "learning_progress"
    __table_args__ = (db.UniqueConstraint("user_id", "resource_id", name="uq_learning_progress_user_resource"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_id = db.Column(db.Integer, db.ForeignKey("learning_resources.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="not_started")  # not_started|in_progress|completed
    hours_spent = db.Column(db.Float, nullable=False, default=0)
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))

    resource = db.relationship("LearningResource")

    def to_dict(self):
        return {"id": self.id, "resource": self.resource.to_dict(), "status": self.status,
                "hours_spent": self.hours_spent, "started_at": iso(self.started_at),
                "completed_at": iso(self.completed_at)}
