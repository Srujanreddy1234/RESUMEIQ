from ..extensions import db
from .base import TimestampMixin, iso


class Job(TimestampMixin, db.Model):
    """A real job posting fetched from a third-party job API. Never generated."""
    __tablename__ = "jobs"
    __table_args__ = (db.UniqueConstraint("source", "external_id", name="uq_jobs_source_external"),)

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(30), nullable=False, index=True)
    external_id = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(255), nullable=False, index=True)
    company = db.Column(db.String(255), index=True)
    location = db.Column(db.String(255))
    work_type = db.Column(db.String(20), nullable=False, default="unknown", index=True)  # remote|hybrid|onsite|unknown
    employment_type = db.Column(db.String(40))
    salary_min = db.Column(db.Integer)
    salary_max = db.Column(db.Integer)
    salary_currency = db.Column(db.String(3))
    salary_text = db.Column(db.String(120))
    salary_is_predicted = db.Column(db.Boolean, nullable=False, default=False)
    experience_min_years = db.Column(db.Float)
    experience_level = db.Column(db.String(20), index=True)  # entry | mid | senior
    education_level = db.Column(db.String(40))
    description = db.Column(db.Text)
    url = db.Column(db.String(1000), nullable=False)
    posted_at = db.Column(db.DateTime(timezone=True), index=True)
    fetched_at = db.Column(db.DateTime(timezone=True), nullable=False)
    search_terms = db.Column(db.String(255))

    skills = db.relationship("JobSkill", cascade="all, delete-orphan", passive_deletes=True)

    SOURCE_LABELS = {"remotive": "Remotive", "arbeitnow": "Arbeitnow", "adzuna": "Adzuna"}

    def skill_names(self, importance=None):
        return sorted(js.skill.name for js in self.skills if importance is None or js.importance == importance)

    def to_dict(self, include_description=False):
        data = {
            "id": self.id,
            "source": self.source,
            "source_label": self.SOURCE_LABELS.get(self.source, self.source),
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "work_type": self.work_type,
            "employment_type": self.employment_type,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "salary_text": self.salary_text,
            "salary_is_predicted": self.salary_is_predicted,
            "experience_min_years": self.experience_min_years,
            "experience_level": self.experience_level,
            "skills": self.skill_names(),
            "url": self.url,
            "posted_at": iso(self.posted_at),
            "fetched_at": iso(self.fetched_at),
        }
        if include_description:
            data["description"] = self.description
            data["required_skills"] = self.skill_names("required")
            data["preferred_skills"] = self.skill_names("preferred")
        return data


class JobSkill(db.Model):
    __tablename__ = "job_skills"
    __table_args__ = (db.UniqueConstraint("job_id", "skill_id", name="uq_job_skills_job_skill"),)

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    importance = db.Column(db.String(20), nullable=False, default="required")  # required | preferred

    skill = db.relationship("Skill")


class JobSourceFetch(db.Model):
    """Cache bookkeeping so we respect provider rate limits/terms."""
    __tablename__ = "job_source_fetches"
    __table_args__ = (db.Index("ix_job_source_fetches_lookup", "source", "query_key", "fetched_at"),)

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(30), nullable=False)
    query_key = db.Column(db.String(255), nullable=False)
    fetched_at = db.Column(db.DateTime(timezone=True), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    result_count = db.Column(db.Integer, nullable=False, default=0)


class JobMatch(db.Model):
    __tablename__ = "job_matches"
    __table_args__ = (db.UniqueConstraint("user_id", "job_id", name="uq_job_matches_user_job"),
                      db.Index("ix_job_matches_user_score", "user_id", "score"))

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_version_id = db.Column(db.Integer, db.ForeignKey("resume_versions.id", ondelete="SET NULL"))
    score = db.Column(db.Integer, nullable=False)
    skills_score = db.Column(db.Integer, nullable=False, default=0)
    experience_score = db.Column(db.Integer, nullable=False, default=0)
    education_score = db.Column(db.Integer, nullable=False, default=0)
    title_score = db.Column(db.Integer, nullable=False, default=0)
    location_score = db.Column(db.Integer, nullable=False, default=0)
    matched_skills = db.Column(db.JSON, nullable=False, default=list)
    missing_skills = db.Column(db.JSON, nullable=False, default=list)
    explanation = db.Column(db.JSON, nullable=False, default=dict)
    profile_signature = db.Column(db.String(64))
    computed_at = db.Column(db.DateTime(timezone=True), nullable=False)

    job = db.relationship("Job")

    def to_dict(self):
        return {
            "score": self.score,
            "components": {
                "skills": self.skills_score, "experience": self.experience_score,
                "education": self.education_score, "title": self.title_score, "location": self.location_score,
            },
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "explanation": self.explanation,
            "computed_at": iso(self.computed_at),
        }


class SavedJob(TimestampMixin, db.Model):
    __tablename__ = "saved_jobs"
    __table_args__ = (db.UniqueConstraint("user_id", "job_id", name="uq_saved_jobs_user_job"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    notes = db.Column(db.Text)

    job = db.relationship("Job")


class JobDescription(TimestampMixin, db.Model):
    """A job description pasted by the user and analysed."""
    __tablename__ = "job_descriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    company = db.Column(db.String(200))
    raw_text = db.Column(db.Text, nullable=False)
    parsed = db.Column(db.JSON, nullable=False, default=dict)
    ai_used = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self, include_text=False):
        data = {"id": self.id, "title": self.title, "company": self.company, "parsed": self.parsed,
                "ai_used": self.ai_used, "created_at": iso(self.created_at)}
        if include_text:
            data["raw_text"] = self.raw_text
        return data
