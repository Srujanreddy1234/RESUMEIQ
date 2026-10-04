"""Request validation schemas."""
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import STAGES
from ..security import normalize_email, safe_url


class Strict(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _url(v):
    return safe_url(v) if v else None


class RegisterIn(Strict):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)
    confirm_password: str = Field(max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return normalize_email(v)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v):
        if "<" in v or ">" in v:
            raise ValueError("Name contains invalid characters.")
        return v


class LoginIn(Strict):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)
    remember_me: bool = False


class ForgotIn(Strict):
    email: str = Field(max_length=255)


class ResetIn(Strict):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(max_length=128)
    confirm_password: str = Field(max_length=128)


class ChangePasswordIn(Strict):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)
    confirm_password: str = Field(max_length=128)


class AccountUpdateIn(Strict):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    email: Optional[str] = Field(default=None, max_length=255)
    current_password: Optional[str] = Field(default=None, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return normalize_email(v) if v else v


class DeleteAccountIn(Strict):
    password: str = Field(max_length=128)
    confirm: Literal["DELETE"]


class ProfileIn(Strict):
    headline: Optional[str] = Field(default=None, max_length=160)
    bio: Optional[str] = Field(default=None, max_length=2000)
    target_career: Optional[str] = Field(default=None, max_length=120)
    years_experience: Optional[float] = Field(default=None, ge=0, le=60)
    location: Optional[str] = Field(default=None, max_length=120)
    education_summary: Optional[str] = Field(default=None, max_length=255)
    preferred_industries: Optional[List[str]] = Field(default=None, max_length=10)
    career_interests: Optional[List[str]] = Field(default=None, max_length=15)
    preferred_work_type: Optional[Literal["any", "remote", "hybrid", "onsite"]] = None
    salary_min: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    salary_max: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    salary_currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    weekly_study_hours: Optional[int] = Field(default=None, ge=1, le=80)
    linkedin_url: Optional[str] = Field(default=None, max_length=255)
    github_url: Optional[str] = Field(default=None, max_length=255)
    theme: Optional[Literal["dark", "light", "system"]] = None
    notify_analysis: Optional[bool] = None
    notify_learning: Optional[bool] = None
    notify_applications: Optional[bool] = None
    notify_interviews: Optional[bool] = None
    notify_jobs: Optional[bool] = None

    _urls = field_validator("linkedin_url", "github_url")(classmethod(lambda cls, v: _url(v)))

    @field_validator("preferred_industries", "career_interests")
    @classmethod
    def _tags(cls, v):
        return [t.strip()[:60] for t in v if t and t.strip()] if v is not None else v


class GoalIn(Strict):
    target_role: str = Field(min_length=2, max_length=120)
    target_date: Optional[date] = None
    weekly_hours: Optional[int] = Field(default=None, ge=1, le=80)
    is_primary: bool = False
    status: Literal["active", "achieved", "paused"] = "active"
    notes: Optional[str] = Field(default=None, max_length=2000)


class EducationIn(Strict):
    institution: str = Field(min_length=2, max_length=200)
    degree: Optional[str] = Field(default=None, max_length=160)
    field_of_study: Optional[str] = Field(default=None, max_length=160)
    graduation_year: Optional[int] = Field(default=None, ge=1950, le=2100)
    gpa: Optional[str] = Field(default=None, max_length=20)


class ExperienceIn(Strict):
    company: str = Field(min_length=1, max_length=200)
    title: Optional[str] = Field(default=None, max_length=160)
    kind: Literal["job", "internship"] = "job"
    start_date: Optional[str] = Field(default=None, max_length=20)
    end_date: Optional[str] = Field(default=None, max_length=20)
    description: Optional[str] = Field(default=None, max_length=4000)


class ProjectIn(Strict):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    technologies: List[str] = Field(default_factory=list, max_length=25)
    url: Optional[str] = Field(default=None, max_length=255)
    _u = field_validator("url")(classmethod(lambda cls, v: _url(v)))


class CertificationIn(Strict):
    name: str = Field(min_length=2, max_length=200)
    issuer: Optional[str] = Field(default=None, max_length=160)
    issued_date: Optional[date] = None
    credential_url: Optional[str] = Field(default=None, max_length=255)
    status: Literal["earned", "in_progress", "planned"] = "earned"
    _u = field_validator("credential_url")(classmethod(lambda cls, v: _url(v)))


class UserSkillIn(Strict):
    skill: str = Field(min_length=1, max_length=60)
    level: int = Field(ge=1, le=5)


class ResumeRenameIn(Strict):
    name: str = Field(min_length=1, max_length=120)


class AnalysisIn(Strict):
    resume_version_id: int
    target_role: str = Field(min_length=2, max_length=120)
    job_description_id: Optional[int] = None


class JDIn(Strict):
    title: str = Field(min_length=2, max_length=200)
    company: Optional[str] = Field(default=None, max_length=200)
    text: str = Field(min_length=80, max_length=30000)

    @field_validator("text")
    @classmethod
    def _looks_like_jd(cls, v):
        if len(v.split()) < 15:
            raise ValueError("This doesn't look like a full job description. Paste the complete posting.")
        return v


class ATSIn(Strict):
    resume_version_id: int
    job_title: str = Field(min_length=2, max_length=200)
    job_description: Optional[str] = Field(default=None, max_length=30000)
    job_description_id: Optional[int] = None
    company: Optional[str] = Field(default=None, max_length=200)


class ImproveIn(Strict):
    resume_version_id: int
    scope: Literal["entire", "bullet", "summary", "skills", "projects", "experience"] = "entire"
    bullet: Optional[str] = Field(default=None, max_length=600)
    target_role: Optional[str] = Field(default=None, max_length=120)


class RoadmapIn(Strict):
    target_role: str = Field(min_length=2, max_length=120)
    weekly_hours: Optional[int] = Field(default=None, ge=1, le=80)


class ItemStatusIn(Strict):
    status: Literal["not_started", "in_progress", "completed"]


class ProgressIn(Strict):
    status: Literal["not_started", "in_progress", "completed"]
    hours_spent: Optional[float] = Field(default=None, ge=0, le=1000)


class ProjectDoneIn(Strict):
    title: str = Field(min_length=2, max_length=200)
    technologies: List[str] = Field(default_factory=list, max_length=20)
    url: Optional[str] = Field(default=None, max_length=255)
    _u = field_validator("url")(classmethod(lambda cls, v: _url(v)))


class InterviewIn(Strict):
    mode: Literal["prep", "mock"] = "prep"
    target_role: str = Field(min_length=2, max_length=120)
    categories: List[Literal["technical", "behavioral", "hr", "project", "system_design", "dsa"]] = Field(
        default_factory=lambda: ["technical", "behavioral", "project"], min_length=1)
    count: int = Field(default=6, ge=1, le=15)
    job_description_id: Optional[int] = None
    resume_version_id: Optional[int] = None


class AnswerIn(Strict):
    question_id: int
    answer: str = Field(min_length=3, max_length=10000)


class ApplicationIn(Strict):
    company: str = Field(min_length=1, max_length=200)
    position: str = Field(min_length=1, max_length=200)
    job_url: Optional[str] = Field(default=None, max_length=1000)
    salary: Optional[str] = Field(default=None, max_length=80)
    location: Optional[str] = Field(default=None, max_length=160)
    stage: Literal[STAGES] = "wishlist"  # type: ignore[valid-type]
    date_applied: Optional[date] = None
    interview_date: Optional[datetime] = None
    contact_person: Optional[str] = Field(default=None, max_length=160)
    contact_email: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = Field(default=None, max_length=5000)
    job_id: Optional[int] = None
    _u = field_validator("job_url")(classmethod(lambda cls, v: _url(v)))

    @field_validator("contact_email")
    @classmethod
    def _email(cls, v):
        return normalize_email(v) if v else None


class ApplicationPatch(ApplicationIn):
    company: Optional[str] = Field(default=None, min_length=1, max_length=200)
    position: Optional[str] = Field(default=None, min_length=1, max_length=200)
    stage: Optional[Literal[STAGES]] = None  # type: ignore[valid-type]


class MoveIn(Strict):
    stage: Literal[STAGES]  # type: ignore[valid-type]
    position: int = Field(default=0, ge=0, le=10000)


class CoverLetterIn(Strict):
    company: str = Field(min_length=1, max_length=200)
    position: str = Field(min_length=1, max_length=200)
    tone: Literal["formal", "concise", "enthusiastic", "technical"] = "formal"
    resume_version_id: Optional[int] = None
    job_description: Optional[str] = Field(default=None, max_length=30000)
    job_description_id: Optional[int] = None


class CoverLetterUpdate(Strict):
    content: str = Field(min_length=20, max_length=20000)
    company: Optional[str] = Field(default=None, max_length=200)
    position: Optional[str] = Field(default=None, max_length=200)


class SaveJobIn(Strict):
    notes: Optional[str] = Field(default=None, max_length=2000)


class AdminUserPatch(Strict):
    is_active: Optional[bool] = None
    role: Optional[Literal["user", "admin"]] = None
