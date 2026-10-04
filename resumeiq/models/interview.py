from ..extensions import db
from .base import TimestampMixin, iso


class InterviewSession(TimestampMixin, db.Model):
    __tablename__ = "interview_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mode = db.Column(db.String(10), nullable=False)  # prep | mock
    target_role = db.Column(db.String(120), nullable=False)
    job_description_id = db.Column(db.Integer, db.ForeignKey("job_descriptions.id", ondelete="SET NULL"))
    resume_version_id = db.Column(db.Integer, db.ForeignKey("resume_versions.id", ondelete="SET NULL"))
    categories = db.Column(db.JSON, nullable=False, default=list)
    status = db.Column(db.String(20), nullable=False, default="active")  # active | completed
    max_questions = db.Column(db.Integer, nullable=False, default=5)
    overall_score = db.Column(db.Integer)
    summary = db.Column(db.JSON)
    completed_at = db.Column(db.DateTime(timezone=True))

    questions = db.relationship("InterviewQuestion", cascade="all, delete-orphan",
                                order_by="InterviewQuestion.position", passive_deletes=True)

    def to_dict(self, include_questions=True):
        data = {"id": self.id, "mode": self.mode, "target_role": self.target_role,
                "categories": self.categories, "status": self.status, "max_questions": self.max_questions,
                "overall_score": self.overall_score, "summary": self.summary,
                "created_at": iso(self.created_at), "completed_at": iso(self.completed_at),
                "question_count": len(self.questions)}
        if include_questions:
            data["questions"] = [q.to_dict() for q in self.questions]
        return data


class InterviewQuestion(TimestampMixin, db.Model):
    __tablename__ = "interview_questions"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(30), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False, default="medium")
    question = db.Column(db.Text, nullable=False)
    why_asked = db.Column(db.Text)
    strong_answer_points = db.Column(db.JSON, nullable=False, default=list)
    common_mistakes = db.Column(db.JSON, nullable=False, default=list)
    parent_question_id = db.Column(db.Integer, db.ForeignKey("interview_questions.id", ondelete="CASCADE"))
    is_follow_up = db.Column(db.Boolean, nullable=False, default=False)

    answers = db.relationship("InterviewAnswer", cascade="all, delete-orphan", passive_deletes=True,
                              order_by="InterviewAnswer.created_at")

    def to_dict(self):
        latest = self.answers[-1] if self.answers else None
        return {"id": self.id, "position": self.position, "category": self.category,
                "difficulty": self.difficulty, "question": self.question, "why_asked": self.why_asked,
                "strong_answer_points": self.strong_answer_points, "common_mistakes": self.common_mistakes,
                "is_follow_up": self.is_follow_up, "answer": latest.to_dict() if latest else None}


class InterviewAnswer(TimestampMixin, db.Model):
    __tablename__ = "interview_answers"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("interview_questions.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    answer_text = db.Column(db.Text, nullable=False)
    scores = db.Column(db.JSON, nullable=False, default=dict)
    overall_score = db.Column(db.Integer)
    feedback = db.Column(db.Text)
    missing_concepts = db.Column(db.JSON, nullable=False, default=list)
    textual_indicators = db.Column(db.JSON, nullable=False, default=dict)
    evaluation_method = db.Column(db.String(20), nullable=False, default="heuristic")

    def to_dict(self):
        return {"id": self.id, "answer_text": self.answer_text, "scores": self.scores,
                "overall_score": self.overall_score, "feedback": self.feedback,
                "missing_concepts": self.missing_concepts, "textual_indicators": self.textual_indicators,
                "evaluation_method": self.evaluation_method, "created_at": iso(self.created_at)}
