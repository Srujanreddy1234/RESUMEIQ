from ..extensions import db
from .base import TimestampMixin, iso


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    slug = db.Column(db.String(80), nullable=False, unique=True, index=True)
    category = db.Column(db.String(40), nullable=False, index=True)
    description = db.Column(db.Text)
    difficulty = db.Column(db.Integer, nullable=False, default=2)  # 1 easy .. 3 hard
    est_hours = db.Column(db.Integer, nullable=False, default=20)
    is_soft = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "slug": self.slug, "category": self.category,
                "description": self.description, "difficulty": self.difficulty,
                "est_hours": self.est_hours, "is_soft": self.is_soft}


class UserSkill(TimestampMixin, db.Model):
    __tablename__ = "user_skills"
    __table_args__ = (db.UniqueConstraint("user_id", "skill_id", name="uq_user_skills_user_skill"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    level = db.Column(db.Integer, nullable=False, default=2)  # 1..5
    source = db.Column(db.String(20), nullable=False, default="resume")  # resume | self | learning

    skill = db.relationship("Skill")

    def to_dict(self):
        return {"id": self.id, "skill": self.skill.to_dict(), "level": self.level,
                "source": self.source, "created_at": iso(self.created_at)}


class SkillGap(db.Model):
    __tablename__ = "skill_gaps"
    __table_args__ = (db.UniqueConstraint("user_id", "target_role", "skill_id", name="uq_skill_gaps_user_role_skill"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    target_role = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # strong | needs_improvement | missing
    current_level = db.Column(db.Integer, nullable=False, default=0)
    required_level = db.Column(db.Integer, nullable=False, default=3)
    importance = db.Column(db.String(20), nullable=False, default="important")  # core | important | nice
    job_frequency = db.Column(db.Float)  # share of analysed postings that mention the skill
    priority_score = db.Column(db.Float, nullable=False, default=0)
    priority_rank = db.Column(db.Integer)
    evidence = db.Column(db.JSON, nullable=False, default=list)
    computed_at = db.Column(db.DateTime(timezone=True), nullable=False)

    skill = db.relationship("Skill")

    def to_dict(self):
        return {
            "id": self.id,
            "skill": self.skill.to_dict(),
            "target_role": self.target_role,
            "status": self.status,
            "current_level": self.current_level,
            "required_level": self.required_level,
            "importance": self.importance,
            "job_frequency": self.job_frequency,
            "priority_score": round(self.priority_score, 1),
            "priority_rank": self.priority_rank,
            "evidence": self.evidence,
            "computed_at": iso(self.computed_at),
        }
