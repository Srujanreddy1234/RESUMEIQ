from ..extensions import db
from .base import TimestampMixin, iso


class Resume(TimestampMixin, db.Model):
    """A logical resume (e.g. "Backend resume"). Each upload is a ResumeVersion."""
    __tablename__ = "resumes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)

    versions = db.relationship("ResumeVersion", back_populates="resume", cascade="all, delete-orphan",
                               order_by="ResumeVersion.version_number", passive_deletes=True)

    @property
    def latest_version(self):
        return self.versions[-1] if self.versions else None

    def to_dict(self):
        latest = self.latest_version
        return {
            "id": self.id,
            "name": self.name,
            "is_primary": self.is_primary,
            "version_count": len(self.versions),
            "latest_version": latest.to_dict() if latest else None,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }


class ResumeVersion(TimestampMixin, db.Model):
    __tablename__ = "resume_versions"
    __table_args__ = (db.UniqueConstraint("resume_id", "version_number", name="uq_resume_versions_resume_version"),)

    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = db.Column(db.Integer, nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(80), nullable=False, unique=True)
    file_type = db.Column(db.String(10), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    checksum = db.Column(db.String(64), nullable=False)
    extracted_text = db.Column(db.Text)
    word_count = db.Column(db.Integer, nullable=False, default=0)
    # Structured extraction snapshot (contact, education, experience, projects...).
    parsed_data = db.Column(db.JSON)
    parse_method = db.Column(db.String(20))  # ai | heuristic
    latest_score = db.Column(db.Integer)
    last_analyzed_at = db.Column(db.DateTime(timezone=True))

    resume = db.relationship("Resume", back_populates="versions")
    skills = db.relationship("ResumeSkill", cascade="all, delete-orphan", passive_deletes=True)

    def to_dict(self, include_parsed=False):
        data = {
            "id": self.id,
            "resume_id": self.resume_id,
            "version_number": self.version_number,
            "original_filename": self.original_filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "word_count": self.word_count,
            "latest_score": self.latest_score,
            "last_analyzed_at": iso(self.last_analyzed_at),
            "parse_method": self.parse_method,
            "uploaded_at": iso(self.created_at),
        }
        if include_parsed:
            data["parsed_data"] = self.parsed_data
            data["skills"] = sorted({rs.skill.name for rs in self.skills})
        return data


class ResumeSkill(db.Model):
    __tablename__ = "resume_skills"
    __table_args__ = (db.UniqueConstraint("resume_version_id", "skill_id", name="uq_resume_skills_version_skill"),)

    id = db.Column(db.Integer, primary_key=True)
    resume_version_id = db.Column(db.Integer, db.ForeignKey("resume_versions.id", ondelete="CASCADE"),
                                  nullable=False, index=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    source = db.Column(db.String(20), nullable=False, default="taxonomy")
    mentions = db.Column(db.Integer, nullable=False, default=1)

    skill = db.relationship("Skill")


class AnalysisHistory(TimestampMixin, db.Model):
    __tablename__ = "analysis_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_version_id = db.Column(db.Integer, db.ForeignKey("resume_versions.id", ondelete="SET NULL"), index=True)
    job_description_id = db.Column(db.Integer, db.ForeignKey("job_descriptions.id", ondelete="SET NULL"))
    kind = db.Column(db.String(20), nullable=False, default="resume")  # resume | ats | jd_match
    target_role = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False, default="completed")
    overall_score = db.Column(db.Integer)
    # List of {key, label, score, weight, explanation, suggestions}
    score_breakdown = db.Column(db.JSON, nullable=False, default=list)
    # Report details (strengths, improvements, keyword sets...)
    result = db.Column(db.JSON, nullable=False, default=dict)
    skills_identified = db.Column(db.Integer, nullable=False, default=0)
    ai_used = db.Column(db.Boolean, nullable=False, default=False)

    resume_version = db.relationship("ResumeVersion")
    job_description = db.relationship("JobDescription")

    def to_summary(self):
        rv = self.resume_version
        return {
            "id": self.id,
            "kind": self.kind,
            "target_role": self.target_role,
            "overall_score": self.overall_score,
            "skills_identified": self.skills_identified,
            "resume": ({"resume_id": rv.resume_id, "version_id": rv.id, "name": rv.resume.name,
                        "version_number": rv.version_number} if rv else None),
            "job_description": ({"id": self.job_description.id, "title": self.job_description.title,
                                 "company": self.job_description.company} if self.job_description else None),
            "ai_used": self.ai_used,
            "created_at": iso(self.created_at),
        }

    def to_dict(self):
        data = self.to_summary()
        data["score_breakdown"] = self.score_breakdown
        data["result"] = self.result
        return data
