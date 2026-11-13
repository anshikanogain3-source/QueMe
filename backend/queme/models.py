from datetime import datetime

from .extensions import db


class Department(db.Model):
    __tablename__ = "departments"
    department_id = db.Column(db.Integer, primary_key=True)
    department_name = db.Column(db.String(100), unique=True, nullable=False)


class Batch(db.Model):
    __tablename__ = "batches"
    batch_id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.department_id"), nullable=False)
    batch_name = db.Column(db.String(100), nullable=False)
    academic_year = db.Column(db.String(20))


class User(db.Model):
    __tablename__ = "users"
    user_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    account_status = db.Column(db.String(20), nullable=False, default="PENDING")
    department_id = db.Column(db.Integer, db.ForeignKey("departments.department_id"))
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.batch_id"))
    roll_number = db.Column(db.String(30))
    employee_id = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    department = db.relationship("Department")
    batch = db.relationship("Batch")

    def to_public(self):
        course = self.department.department_name if self.department else None
        semester = self.batch.batch_name if self.batch else None
        return {
            "user_id": self.user_id,
            "full_name": self.full_name,
            "email": self.email,
            "role": self.role,
            "account_status": self.account_status,
            "department_id": self.department_id,
            "batch_id": self.batch_id,
            "course": course,
            "semester": semester,
            "academic_year": self.batch.academic_year if self.batch else None,
            "roll_number": self.roll_number,
            "employee_id": self.employee_id,
        }


class QuestionBank(db.Model):
    __tablename__ = "question_bank"
    question_id = db.Column(db.Integer, primary_key=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(30), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    expected_key_points = db.Column(db.Text)
    reference_answer = db.Column(db.Text)
    topics_json = db.Column(db.JSON)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "question_id": self.question_id,
            "created_by": self.created_by,
            "question_text": self.question_text,
            "question_type": self.question_type,
            "difficulty": self.difficulty,
            "expected_key_points": self.expected_key_points,
            "reference_answer": self.reference_answer,
            "topics": self.topics_json or [],
            "is_active": self.is_active,
        }


class Rubric(db.Model):
    __tablename__ = "rubrics"
    rubric_id = db.Column(db.Integer, primary_key=True)
    rubric_name = db.Column(db.String(100), nullable=False)
    rubric_type = db.Column(db.String(30), nullable=False)
    criteria_json = db.Column(db.JSON, nullable=False)
    maximum_score = db.Column(db.Integer, nullable=False, default=10)
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "rubric_id": self.rubric_id,
            "rubric_name": self.rubric_name,
            "rubric_type": self.rubric_type,
            "criteria_json": self.criteria_json,
            "maximum_score": self.maximum_score,
            "created_by": self.created_by,
        }


class InterviewTemplate(db.Model):
    __tablename__ = "interview_templates"
    template_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    duration_minutes = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    questions = db.relationship(
        "TemplateQuestion",
        backref="template",
        order_by="TemplateQuestion.question_order",
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_questions=False):
        data = {
            "template_id": self.template_id,
            "title": self.title,
            "description": self.description,
            "created_by": self.created_by,
            "duration_minutes": self.duration_minutes,
        }
        if include_questions:
            data["questions"] = [q.to_dict() for q in self.questions]
        return data


class TemplateQuestion(db.Model):
    __tablename__ = "template_questions"
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("interview_templates.template_id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question_bank.question_id"), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey("rubrics.rubric_id"))
    question_order = db.Column(db.Integer, nullable=False)
    question = db.relationship("QuestionBank")
    rubric = db.relationship("Rubric")

    def to_dict(self):
        return {
            "id": self.id,
            "template_id": self.template_id,
            "question_id": self.question_id,
            "rubric_id": self.rubric_id,
            "question_order": self.question_order,
            "question": self.question.to_dict() if self.question else None,
            "rubric": self.rubric.to_dict() if self.rubric else None,
        }


class Interview(db.Model):
    __tablename__ = "interviews"
    interview_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    template_id = db.Column(db.Integer, db.ForeignKey("interview_templates.template_id"))
    scheduled_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    ended_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default="SCHEDULED")
    consent_given = db.Column(db.Boolean, default=False)
    final_score = db.Column(db.Numeric(4, 2))
    teacher_remark = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    current_index = db.Column(db.Integer, default=0)

    student = db.relationship("User", foreign_keys=[student_id])
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    template = db.relationship("InterviewTemplate")
    questions = db.relationship(
        "InterviewQuestion",
        order_by="InterviewQuestion.question_order",
        back_populates="interview",
    )
    report = db.relationship("Report", uselist=False)

    def to_dict(self, include_questions=False):
        data = {
            "interview_id": self.interview_id,
            "student_id": self.student_id,
            "student_name": self.student.full_name if self.student else None,
            "teacher_id": self.teacher_id,
            "teacher_name": self.teacher.full_name if self.teacher else None,
            "template_id": self.template_id,
            "template_title": self.template.title if self.template else None,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "status": self.status,
            "consent_given": self.consent_given,
            "final_score": float(self.final_score) if self.final_score is not None else None,
            "teacher_remark": self.teacher_remark,
            "current_index": self.current_index or 0,
        }
        if include_questions:
            data["questions"] = [q.to_dict() for q in self.questions]
        return data


class InterviewQuestion(db.Model):
    __tablename__ = "interview_questions"
    interview_question_id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey("interviews.interview_id"))
    question_id = db.Column(db.Integer, db.ForeignKey("question_bank.question_id"))
    rubric_id = db.Column(db.Integer, db.ForeignKey("rubrics.rubric_id"))
    question_order = db.Column(db.Integer, nullable=False)
    asked_at = db.Column(db.DateTime)
    followup_text = db.Column(db.Text)
    answer_audio_path = db.Column(db.Text)
    transcript = db.Column(db.Text)
    content_score = db.Column(db.Numeric(4, 2))
    delivery_score = db.Column(db.Numeric(4, 2))
    final_ai_score = db.Column(db.Numeric(4, 2))
    teacher_score = db.Column(db.Numeric(4, 2))
    teacher_remark = db.Column(db.Text)
    needs_review = db.Column(db.Boolean, default=False)
    evaluation_json = db.Column(db.JSON)
    is_followup = db.Column(db.Boolean, default=False)

    question = db.relationship("QuestionBank")
    rubric = db.relationship("Rubric")
    interview = db.relationship("Interview", back_populates="questions")
    analysis = db.relationship("AudioAnalysis", uselist=False)
    processing_job = db.relationship("AnswerProcessingJob", uselist=False, back_populates="question")
    reviews = db.relationship("QuestionReview", back_populates="interview_question", order_by="QuestionReview.reviewed_at")

    def to_dict(self):
        return {
            "interview_question_id": self.interview_question_id,
            "interview_id": self.interview_id,
            "question_id": self.question_id,
            "rubric_id": self.rubric_id,
            "question_order": self.question_order,
            "question_text": (self.question.question_text if self.question else self.followup_text),
            "question_type": self.question.question_type if self.question else ("Follow-up" if self.is_followup else None),
            "difficulty": self.question.difficulty if self.question else None,
            "asked_at": self.asked_at.isoformat() if self.asked_at else None,
            "answer_audio_path": self.answer_audio_path,
            "transcript": self.transcript,
            "content_score": float(self.content_score) if self.content_score is not None else None,
            "delivery_score": float(self.delivery_score) if self.delivery_score is not None else None,
            "final_ai_score": float(self.final_ai_score) if self.final_ai_score is not None else None,
            "teacher_score": float(self.teacher_score) if self.teacher_score is not None else None,
            "teacher_remark": self.teacher_remark,
            "needs_review": self.needs_review,
            "evaluation_json": self.evaluation_json,
            "is_followup": self.is_followup,
            "analysis": self.analysis.to_dict() if self.analysis else None,
        }


class AudioAnalysis(db.Model):
    __tablename__ = "audio_analysis"
    analysis_id = db.Column(db.Integer, primary_key=True)
    interview_question_id = db.Column(db.Integer, db.ForeignKey("interview_questions.interview_question_id"))
    transcript = db.Column(db.Text)
    language_detected = db.Column(db.String(20))
    transcription_status = db.Column(db.String(20))
    answer_duration_seconds = db.Column(db.Numeric(8, 2))
    speaking_duration_seconds = db.Column(db.Numeric(8, 2))
    words_per_minute = db.Column(db.Numeric(6, 2))
    pause_count = db.Column(db.Integer)
    total_pause_duration_seconds = db.Column(db.Numeric(8, 2))
    longest_pause_seconds = db.Column(db.Numeric(8, 2))
    filler_word_count = db.Column(db.Integer)
    filler_word_rate = db.Column(db.Numeric(6, 4))
    repetition_count = db.Column(db.Integer)
    speech_ratio = db.Column(db.Numeric(5, 4))
    technical_keywords_found = db.Column(db.JSON)
    filler_words_found = db.Column(db.JSON)
    detected_intent = db.Column(db.String(50))
    audio_quality_status = db.Column(db.String(20))
    background_noise_level = db.Column(db.String(20))
    audio_usable = db.Column(db.Boolean)
    pitch_mean_hz = db.Column(db.Numeric(8, 2))
    pitch_std_hz = db.Column(db.Numeric(8, 2))
    rms_mean = db.Column(db.Numeric(10, 6))
    rms_std = db.Column(db.Numeric(10, 6))
    delivery_score = db.Column(db.Numeric(4, 2))
    analysis_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "analysis_id": self.analysis_id,
            "transcript": self.transcript,
            "language_detected": self.language_detected,
            "transcription_status": self.transcription_status,
            "answer_duration_seconds": float(self.answer_duration_seconds) if self.answer_duration_seconds is not None else None,
            "speaking_duration_seconds": float(self.speaking_duration_seconds) if self.speaking_duration_seconds is not None else None,
            "words_per_minute": float(self.words_per_minute) if self.words_per_minute is not None else None,
            "pause_count": self.pause_count,
            "total_pause_duration_seconds": float(self.total_pause_duration_seconds) if self.total_pause_duration_seconds is not None else None,
            "longest_pause_seconds": float(self.longest_pause_seconds) if self.longest_pause_seconds is not None else None,
            "filler_word_count": self.filler_word_count,
            "filler_word_rate": float(self.filler_word_rate) if self.filler_word_rate is not None else None,
            "repetition_count": self.repetition_count,
            "speech_ratio": float(self.speech_ratio) if self.speech_ratio is not None else None,
            "technical_keywords_found": self.technical_keywords_found,
            "filler_words_found": self.filler_words_found,
            "detected_intent": self.detected_intent,
            "audio_quality_status": self.audio_quality_status,
            "background_noise_level": self.background_noise_level,
            "audio_usable": self.audio_usable,
            "pitch_mean_hz": float(self.pitch_mean_hz) if self.pitch_mean_hz is not None else None,
            "pitch_std_hz": float(self.pitch_std_hz) if self.pitch_std_hz is not None else None,
            "rms_mean": float(self.rms_mean) if self.rms_mean is not None else None,
            "rms_std": float(self.rms_std) if self.rms_std is not None else None,
            "delivery_score": float(self.delivery_score) if self.delivery_score is not None else None,
        }


class AnswerProcessingJob(db.Model):
    __tablename__ = "answer_processing_jobs"
    __table_args__ = (
        db.UniqueConstraint("interview_question_id", name="uq_answer_job_question"),
        db.Index("ix_answer_job_status_available", "status", "available_at"),
    )

    job_id = db.Column(db.Integer, primary_key=True)
    interview_question_id = db.Column(
        db.Integer,
        db.ForeignKey("interview_questions.interview_question_id"),
        nullable=False,
    )
    submission_id = db.Column(db.String(64), nullable=False, unique=True)
    audio_path = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(24), nullable=False, default="QUEUED")
    stage = db.Column(db.String(24), nullable=False, default="TRANSCRIPTION")
    outcome = db.Column(db.String(24))
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    available_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    locked_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    last_error_code = db.Column(db.String(60))
    last_error_message = db.Column(db.String(300))

    question = db.relationship("InterviewQuestion", back_populates="processing_job")

    def to_status_dict(self):
        return {
            "job_id": self.job_id,
            "interview_question_id": self.interview_question_id,
            "status": self.status,
            "stage": self.stage,
            "outcome": self.outcome,
            "attempt_count": self.attempt_count,
            "available_at": self.available_at.isoformat() if self.available_at else None,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
        }


class Report(db.Model):
    __tablename__ = "reports"
    report_id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey("interviews.interview_id"), unique=True)
    ai_final_score = db.Column(db.Numeric(4, 2))
    teacher_score = db.Column(db.Numeric(4, 2))
    final_score = db.Column(db.Numeric(4, 2))
    score_source = db.Column(db.String(30))
    report_status = db.Column(db.String(30))
    teacher_remark = db.Column(db.Text)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    interview = db.relationship("Interview", overlaps="report")

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "interview_id": self.interview_id,
            "ai_final_score": float(self.ai_final_score) if self.ai_final_score is not None else None,
            "teacher_score": float(self.teacher_score) if self.teacher_score is not None else None,
            "final_score": float(self.final_score) if self.final_score is not None else None,
            "score_source": self.score_source,
            "report_status": self.report_status,
            "teacher_remark": self.teacher_remark,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


class QuestionReview(db.Model):
    __tablename__ = "question_reviews"
    review_id = db.Column(db.Integer, primary_key=True)
    interview_question_id = db.Column(
        db.Integer, db.ForeignKey("interview_questions.interview_question_id"), nullable=False
    )
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    rubric_version = db.Column(db.String(40))
    ai_score = db.Column(db.Numeric(4, 2))
    teacher_score = db.Column(db.Numeric(4, 2))
    ai_criteria_json = db.Column(db.JSON)
    teacher_criteria_json = db.Column(db.JSON)
    teacher_remark = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    interview_question = db.relationship("InterviewQuestion", back_populates="reviews")
    reviewer = db.relationship("User")


class SystemSetting(db.Model):
    __tablename__ = "system_settings"
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(100), nullable=False)
