"""Pydantic schemas every AI response is validated against."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _clip(items, n):
    return [i for i in items if i][:n]


class EducationItem(BaseModel):
    institution: str = ""
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    graduation_year: Optional[int] = None
    gpa: Optional[str] = None


class ExperienceItem(BaseModel):
    company: str = ""
    title: Optional[str] = None
    kind: Literal["job", "internship"] = "job"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)


class ProjectItem(BaseModel):
    name: str = ""
    description: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)


class ResumeExtraction(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    links: List[str] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    programming_languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    experience: List[ExperienceItem] = Field(default_factory=list)
    achievements: List[str] = Field(default_factory=list)
    publications: List[str] = Field(default_factory=list)

    @field_validator("skills", "programming_languages", "frameworks", "tools")
    @classmethod
    def _limit_skills(cls, v):
        return _clip([s.strip() for s in v if isinstance(s, str) and s.strip()], 80)

    def is_meaningful(self):
        return bool(self.skills or self.programming_languages or self.experience or self.education or self.projects)


class SectionFeedback(BaseModel):
    section: str
    comment: str


class ResumeFeedback(BaseModel):
    summary: str
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    section_feedback: List[SectionFeedback] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def _non_empty(cls, v):
        if not v or len(v.strip()) < 20:
            raise ValueError("summary must be a meaningful sentence")
        return v.strip()


class ImprovementItem(BaseModel):
    section: str
    original: str
    improved: str
    explanation: str
    needs_metric: bool = False


class ImprovementResult(BaseModel):
    items: List[ImprovementItem] = Field(default_factory=list)
    improved_summary: Optional[str] = None
    skills_section_advice: List[str] = Field(default_factory=list)


class JDExtraction(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    experience_years: Optional[float] = None
    education: Optional[str] = None
    certifications: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    salary_text: Optional[str] = None
    work_type: Optional[Literal["remote", "hybrid", "onsite", "unknown"]] = None


class InterviewQuestionItem(BaseModel):
    category: Literal["technical", "behavioral", "hr", "project", "system_design", "dsa"]
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    question: str
    why_asked: str
    strong_answer_points: List[str] = Field(default_factory=list)
    common_mistakes: List[str] = Field(default_factory=list)


class InterviewQuestionSet(BaseModel):
    questions: List[InterviewQuestionItem]

    @field_validator("questions")
    @classmethod
    def _non_empty(cls, v):
        if not v:
            raise ValueError("at least one question is required")
        return v


class AnswerScores(BaseModel):
    communication: int = Field(ge=0, le=10)
    technical_accuracy: int = Field(ge=0, le=10)
    relevance: int = Field(ge=0, le=10)
    structure: int = Field(ge=0, le=10)


class AnswerEvaluation(BaseModel):
    scores: AnswerScores
    feedback: str
    missing_concepts: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    follow_up_question: Optional[str] = None


class InterviewSummary(BaseModel):
    summary: str
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    missing_concepts: List[str] = Field(default_factory=list)


class CoverLetterOut(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def _long_enough(cls, v):
        if len(v.strip()) < 300:
            raise ValueError("cover letter is too short")
        return v.strip()


class ProjectIdea(BaseModel):
    title: str
    difficulty: Literal["beginner", "intermediate", "advanced"]
    skills: List[str]
    technologies: List[str] = Field(default_factory=list)
    features: List[str] = Field(default_factory=list)
    duration_weeks: int = Field(ge=1, le=26)
    resume_value: str


class ProjectIdeas(BaseModel):
    projects: List[ProjectIdea]


class InsightItem(BaseModel):
    text: str
    evidence_keys: List[str] = Field(default_factory=list)


class CareerInsightsOut(BaseModel):
    insights: List[InsightItem]


class SalaryInterpretation(BaseModel):
    interpretation: str
    caveats: List[str] = Field(default_factory=list)


class RoadmapTopic(BaseModel):
    skill: str
    topics: List[str] = Field(default_factory=list)


class RoadmapTopics(BaseModel):
    items: List[RoadmapTopic]


class ResumeTips(BaseModel):
    tips: List[str]
