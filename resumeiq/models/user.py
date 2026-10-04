from ..extensions import db
from .base import TimestampMixin, iso


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Bumped on password change/reset to invalidate every issued token.
    token_version = db.Column(db.Integer, nullable=False, default=1)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    last_login_at = db.Column(db.DateTime(timezone=True))

    profile = db.relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")

    @property
    def is_admin(self):
        return self.role == "admin"

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "created_at": iso(self.created_at),
            "last_login_at": iso(self.last_login_at),
        }


class Profile(TimestampMixin, db.Model):
    __tablename__ = "profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    avatar_filename = db.Column(db.String(80))
    headline = db.Column(db.String(160))
    bio = db.Column(db.Text)
    target_career = db.Column(db.String(120))
    years_experience = db.Column(db.Float)
    location = db.Column(db.String(120))
    education_summary = db.Column(db.String(255))
    preferred_industries = db.Column(db.JSON, nullable=False, default=list)
    career_interests = db.Column(db.JSON, nullable=False, default=list)
    preferred_work_type = db.Column(db.String(20), nullable=False, default="any")
    salary_min = db.Column(db.Integer)
    salary_max = db.Column(db.Integer)
    salary_currency = db.Column(db.String(3), nullable=False, default="USD")
    weekly_study_hours = db.Column(db.Integer, nullable=False, default=8)
    linkedin_url = db.Column(db.String(255))
    github_url = db.Column(db.String(255))
    theme = db.Column(db.String(10), nullable=False, default="dark")
    # Notification preferences
    notify_analysis = db.Column(db.Boolean, nullable=False, default=True)
    notify_learning = db.Column(db.Boolean, nullable=False, default=True)
    notify_applications = db.Column(db.Boolean, nullable=False, default=True)
    notify_interviews = db.Column(db.Boolean, nullable=False, default=True)
    notify_jobs = db.Column(db.Boolean, nullable=False, default=True)

    user = db.relationship("User", back_populates="profile")

    COMPLETENESS_FIELDS = (
        "headline", "target_career", "years_experience", "location", "education_summary",
        "preferred_industries", "preferred_work_type", "salary_min", "linkedin_url", "avatar_filename",
    )

    def completeness(self):
        filled = 0
        for field in self.COMPLETENESS_FIELDS:
            value = getattr(self, field)
            if field == "preferred_work_type":
                value = value if value and value != "any" else None
            if value not in (None, "", [], 0) or (field == "years_experience" and value == 0):
                filled += 1
        return round(100 * filled / len(self.COMPLETENESS_FIELDS))

    def to_dict(self):
        return {
            "headline": self.headline,
            "bio": self.bio,
            "target_career": self.target_career,
            "years_experience": self.years_experience,
            "location": self.location,
            "education_summary": self.education_summary,
            "preferred_industries": self.preferred_industries or [],
            "career_interests": self.career_interests or [],
            "preferred_work_type": self.preferred_work_type,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "weekly_study_hours": self.weekly_study_hours,
            "linkedin_url": self.linkedin_url,
            "github_url": self.github_url,
            "theme": self.theme,
            "has_avatar": bool(self.avatar_filename),
            "notifications": {
                "analysis": self.notify_analysis,
                "learning": self.notify_learning,
                "applications": self.notify_applications,
                "interviews": self.notify_interviews,
                "jobs": self.notify_jobs,
            },
            "completeness": self.completeness(),
        }


class PasswordResetToken(TimestampMixin, db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Only a SHA-256 hash of the token is stored.
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True))


class TokenBlocklist(db.Model):
    __tablename__ = "token_blocklist"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), nullable=False, unique=True)
    token_type = db.Column(db.String(10), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)


class CareerGoal(TimestampMixin, db.Model):
    __tablename__ = "career_goals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_role = db.Column(db.String(120), nullable=False)
    target_date = db.Column(db.Date)
    weekly_hours = db.Column(db.Integer)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    notes = db.Column(db.Text)

    def to_dict(self):
        return {
            "id": self.id,
            "target_role": self.target_role,
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "weekly_hours": self.weekly_hours,
            "is_primary": self.is_primary,
            "status": self.status,
            "notes": self.notes,
            "created_at": iso(self.created_at),
        }


class Education(TimestampMixin, db.Model):
    __tablename__ = "education"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    institution = db.Column(db.String(200), nullable=False)
    degree = db.Column(db.String(160))
    field_of_study = db.Column(db.String(160))
    graduation_year = db.Column(db.Integer)
    gpa = db.Column(db.String(20))
    source = db.Column(db.String(20), nullable=False, default="manual")

    def to_dict(self):
        return {"id": self.id, "institution": self.institution, "degree": self.degree,
                "field_of_study": self.field_of_study, "graduation_year": self.graduation_year,
                "gpa": self.gpa, "source": self.source}


class Experience(TimestampMixin, db.Model):
    __tablename__ = "experiences"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(160))
    kind = db.Column(db.String(20), nullable=False, default="job")  # job | internship
    start_date = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    description = db.Column(db.Text)
    source = db.Column(db.String(20), nullable=False, default="manual")

    def to_dict(self):
        return {"id": self.id, "company": self.company, "title": self.title, "kind": self.kind,
                "start_date": self.start_date, "end_date": self.end_date,
                "description": self.description, "source": self.source}


class UserProject(TimestampMixin, db.Model):
    __tablename__ = "user_projects"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    technologies = db.Column(db.JSON, nullable=False, default=list)
    url = db.Column(db.String(255))
    source = db.Column(db.String(20), nullable=False, default="manual")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "description": self.description,
                "technologies": self.technologies or [], "url": self.url, "source": self.source}


class Certification(TimestampMixin, db.Model):
    __tablename__ = "certifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    issuer = db.Column(db.String(160))
    issued_date = db.Column(db.Date)
    credential_url = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default="earned")  # earned | in_progress | planned
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="SET NULL"))
    source = db.Column(db.String(20), nullable=False, default="manual")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "issuer": self.issuer,
                "issued_date": self.issued_date.isoformat() if self.issued_date else None,
                "credential_url": self.credential_url, "status": self.status, "source": self.source}
