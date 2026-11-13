from datetime import datetime
import json
import math

from flask import Blueprint, g, jsonify, send_file
from sqlalchemy.exc import IntegrityError

from ..api_errors import api_error, json_object
from ..authz import login_required
from ..extensions import db
from ..models import Interview, InterviewQuestion, QuestionReview, Report
from ..services.answer_jobs import processing_summary
from ..services.reports import (
    _valid_score,
    answer_processing_status,
    build_excel,
    build_pdf,
    build_report_analytics,
    generate_interview_report,
    get_interview_score_weights,
    question_analysis_status,
)

bp = Blueprint("reports", __name__)


def _authorized_interview(interview_id):
    interview = db.session.get(Interview, interview_id)
    if interview is None:
        return None, api_error("Interview not found.", "interview_not_found", 404)
    allowed = (
        g.user.role == "admin"
        or (g.user.role == "student" and interview.student_id == g.user.user_id)
        or (g.user.role == "teacher" and interview.teacher_id == g.user.user_id)
    )
    if not allowed:
        return None, api_error("You do not have permission to access this interview report.", "forbidden", 403)
    return interview, None


def _teacher_review_payload(row):
    review = next((item for item in reversed(row.reviews) if (
        item.teacher_score is not None or item.teacher_remark or item.teacher_criteria_json
    )), None)
    if review is None:
        return None
    ai_criteria = review.ai_criteria_json if isinstance(review.ai_criteria_json, dict) else {}
    teacher_criteria = review.teacher_criteria_json if isinstance(review.teacher_criteria_json, dict) else {}
    differences = {
        name: round(float(teacher_criteria[name]) - float(ai_criteria[name]), 2)
        for name in ai_criteria.keys() & teacher_criteria.keys()
        if _valid_score(ai_criteria[name]) is not None and _valid_score(teacher_criteria[name]) is not None
    }
    return {
        "reviewer_name": review.reviewer.full_name if review.reviewer else None,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "ai_score": float(review.ai_score) if review.ai_score is not None else None,
        "teacher_score": float(review.teacher_score) if review.teacher_score is not None else None,
        "score_difference": round(float(review.teacher_score) - float(review.ai_score), 2)
        if review.teacher_score is not None and review.ai_score is not None else None,
        "ai_criteria_scores": ai_criteria,
        "teacher_criteria_scores": teacher_criteria,
        "criterion_differences": differences,
        "teacher_remark": review.teacher_remark,
    }


def _report_payload(interview, report):
    questions = InterviewQuestion.query.filter_by(interview_id=interview.interview_id).order_by(
        InterviewQuestion.question_order
    ).all()
    content_weight, delivery_weight = get_interview_score_weights(questions)
    analytics = build_report_analytics(questions)
    analytics["teacher_reviewed_answers"] = sum(_teacher_review_payload(row) is not None for row in questions)
    return {
        **report.to_dict(),
        "student_name": interview.student.full_name if interview.student else None,
        "teacher_name": interview.teacher.full_name if interview.teacher else None,
        "template_title": interview.template.title if interview.template else None,
        "score_weights": {"content_weight": content_weight, "delivery_weight": delivery_weight},
        "score_method": "Question final AI score = content score × content weight + delivery score × delivery weight; both component scores use a 0–10 scale.",
        "answer_processing": processing_summary(interview),
        **analytics,
        "questions": [
            {
                "interview_question_id": row.interview_question_id,
                "question_order": row.question_order,
                "question_text": row.question.question_text if row.question else (row.followup_text or ""),
                "topics": row.question.topics_json or [] if row.question else [],
                "is_followup": bool(row.is_followup),
                "transcript": row.transcript,
                "content_score": float(row.content_score) if row.content_score is not None else None,
                "delivery_score": float(row.delivery_score) if row.delivery_score is not None else None,
                "final_ai_score": float(row.final_ai_score) if row.final_ai_score is not None else None,
                "teacher_score": float(row.teacher_score) if row.teacher_score is not None else None,
                "final_score": float(row.teacher_score if row.teacher_score is not None else row.final_ai_score)
                if row.teacher_score is not None or row.final_ai_score is not None else None,
                "teacher_remark": row.teacher_remark,
                "needs_review": bool(row.needs_review),
                "evaluation": row.evaluation_json,
                "analysis_status": question_analysis_status(row),
                "processing_status": answer_processing_status(row),
                "teacher_review": _teacher_review_payload(row),
                "audio_analysis": {
                    **row.analysis.to_dict(),
                    "word_timestamps": (row.analysis.analysis_json or {}).get("word_timestamps", [])
                    if isinstance(row.analysis.analysis_json, dict) else [],
                } if row.analysis else None,
                "audio_url": f"/interviews/{interview.interview_id}/questions/{row.interview_question_id}/audio"
                if row.answer_audio_path else None,
            }
            for row in questions
        ],
    }


def _get_or_create_report(interview_id, *, commit_if_created=True):
    interview = (
        db.session.query(Interview)
        .filter_by(interview_id=interview_id)
        .with_for_update()
        .first()
    )
    report = Report.query.filter_by(interview_id=interview_id).first()
    if report is None:
        report = generate_interview_report(interview)
        try:
            if commit_if_created:
                db.session.commit()
            else:
                db.session.flush()
        except IntegrityError:
            db.session.rollback()
            interview = db.session.get(Interview, interview_id)
            report = Report.query.filter_by(interview_id=interview_id).first()
            if report is None:
                raise
    return interview, report
def _score(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, f"{field} must be a finite number from 0 to 10."
    score = float(value)
    if not math.isfinite(score) or not 0 <= score <= 10:
        return None, f"{field} must be a finite number from 0 to 10."
    return score, None


@bp.get("/interviews/<int:interview_id>/report")
@login_required()
def get_report(interview_id):
    interview, error = _authorized_interview(interview_id)
    if error is not None:
        return error
    if interview.status != "COMPLETED":
        return api_error("The report is available after the interview is completed.", "report_not_ready", 409)
    interview, report = _get_or_create_report(interview_id)
    return jsonify(_report_payload(interview, report))


@bp.get("/students/me/progress")
@login_required("student")
def student_progress():
    interviews = Interview.query.filter_by(student_id=g.user.user_id, status="COMPLETED").order_by(
        Interview.ended_at.asc().nullslast(), Interview.interview_id
    ).all()
    history = []
    for interview in interviews:
        questions = InterviewQuestion.query.filter_by(interview_id=interview.interview_id).order_by(
            InterviewQuestion.question_order
        ).all()
        analytics = build_report_analytics(questions)
        content_scores = [score for row in questions if (score := _valid_score(row.content_score)) is not None]
        delivery_scores = [score for row in questions if (score := _valid_score(row.delivery_score)) is not None]
        history.append({
            "interview_id": interview.interview_id,
            "interview_date": interview.ended_at.isoformat() if interview.ended_at else None,
            "template_title": interview.template.title if interview.template else "Interview",
            "template_id": interview.template_id,
            "overall_score": float(interview.final_score) if interview.final_score is not None else None,
            "content_score": round(sum(content_scores) / len(content_scores), 2) if content_scores else None,
            "delivery_score": round(sum(delivery_scores) / len(delivery_scores), 2) if delivery_scores else None,
            "audio_summary": analytics["audio_summary"],
            "topic_analysis": analytics["topic_analysis"],
            "analysis_coverage": analytics["analysis_coverage"],
            "rubric_versions": sorted({
                (row.evaluation_json or {}).get("rubric_version")
                for row in questions
                if isinstance(row.evaluation_json, dict) and (row.evaluation_json or {}).get("rubric_version")
            }),
            "question_difficulties": sorted({
                row.question.difficulty for row in questions if row.question and row.question.difficulty
            }),
        })
    for index, item in enumerate(history):
        if index == 0:
            item["comparison_to_previous"] = {"comparable": None, "reasons": ["No earlier completed interview."]}
            continue
        previous = history[index - 1]
        reasons = []
        if item["template_id"] != previous["template_id"]:
            reasons.append("Interview template differs.")
        if item["rubric_versions"] != previous["rubric_versions"]:
            reasons.append("Rubric versions differ.")
        if item["question_difficulties"] != previous["question_difficulties"]:
            reasons.append("Question difficulty mix differs.")
        current_coverage = item["analysis_coverage"]["coverage"]["overall"]["percentage"]
        previous_coverage = previous["analysis_coverage"]["coverage"]["overall"]["percentage"]
        if current_coverage is None or previous_coverage is None or abs(current_coverage - previous_coverage) > 20:
            reasons.append("Analysis coverage differs materially or is unavailable.")
        item["comparison_to_previous"] = {"comparable": not reasons, "reasons": reasons}
    return jsonify({"interviews": history, "sample_count": len(history)})


@bp.patch("/interviews/<int:interview_id>/report")
@login_required("teacher", "admin")
def review_report(interview_id):
    interview, error = _authorized_interview(interview_id)
    if error is not None:
        return error
    if interview.status != "COMPLETED":
        return api_error("Only completed interviews can be reviewed.", "report_not_ready", 409)
    data = json_object()
    if data is None or not data:
        return api_error("Provide teacher_score, teacher_remark, or question_reviews.", "invalid_review", 400)
    allowed_fields = {"teacher_score", "teacher_remark", "question_reviews"}
    if set(data) - allowed_fields:
        return api_error("Review contains unsupported fields.", "invalid_review", 400)
    overall_review_submitted = "teacher_score" in data or "teacher_remark" in data

    interview, report = _get_or_create_report(interview_id, commit_if_created=False)

    if "teacher_score" in data:
        value = data["teacher_score"]
        if value is None:
            report.teacher_score = None
        else:
            score, validation_error = _score(value, "teacher_score")
            if validation_error:
                return api_error(validation_error, "invalid_teacher_score", 400)
            report.teacher_score = score
    if "teacher_remark" in data:
        remark = data["teacher_remark"]
        if remark is not None and (not isinstance(remark, str) or len(remark) > 5000):
            return api_error("teacher_remark must be a string of at most 5000 characters or null.", "invalid_teacher_remark", 400)
        report.teacher_remark = remark.strip() if isinstance(remark, str) and remark.strip() else None

    reviews = data.get("question_reviews", [])
    if not isinstance(reviews, list):
        return api_error("question_reviews must be an array.", "invalid_question_reviews", 400)
    by_id = {q.interview_question_id: q for q in InterviewQuestion.query.filter_by(interview_id=interview_id).all()}
    seen = set()
    for item in reviews:
        if not isinstance(item, dict) or isinstance(item.get("interview_question_id"), bool):
            return api_error("Each question review needs an interview_question_id.", "invalid_question_reviews", 400)
        try:
            question_id = int(item.get("interview_question_id"))
        except (TypeError, ValueError):
            return api_error("interview_question_id must be an integer.", "invalid_question_reviews", 400)
        if question_id not in by_id or question_id in seen or set(item) - {"interview_question_id", "teacher_score", "teacher_remark", "teacher_criteria_scores"}:
            return api_error("Question review identifies an invalid or duplicate question.", "invalid_question_reviews", 400)
        question = by_id[question_id]
        teacher_criteria = None
        if "teacher_criteria_scores" in item:
            raw_criteria = item["teacher_criteria_scores"]
            if not isinstance(raw_criteria, dict):
                return api_error("teacher_criteria_scores must be an object of criterion scores from 0 to 10.", "invalid_question_reviews", 400)
            ai_criteria = (question.evaluation_json or {}).get("criteria_scores", {}) if isinstance(question.evaluation_json, dict) else {}
            if set(raw_criteria) - set(ai_criteria):
                return api_error("Teacher rubric review contains an unknown criterion.", "invalid_question_reviews", 400)
            teacher_criteria = {}
            for criterion, value in raw_criteria.items():
                if value is None:
                    continue
                score, validation_error = _score(value, f"teacher_criteria_scores.{criterion}")
                if validation_error:
                    return api_error(validation_error, "invalid_teacher_score", 400)
                teacher_criteria[criterion] = score
        if "teacher_score" in item:
            value = item["teacher_score"]
            if value is None:
                if not teacher_criteria:
                    question.teacher_score = None
            else:
                score, validation_error = _score(value, "question teacher_score")
                if validation_error:
                    return api_error(validation_error, "invalid_teacher_score", 400)
                question.teacher_score = score
        if "teacher_remark" in item:
            remark = item["teacher_remark"]
            if remark is not None and (not isinstance(remark, str) or len(remark) > 5000):
                return api_error("Question teacher_remark must be a string of at most 5000 characters or null.", "invalid_teacher_remark", 400)
            question.teacher_remark = remark.strip() if isinstance(remark, str) and remark.strip() else None
        if any(key in item for key in ("teacher_score", "teacher_criteria_scores", "teacher_remark")):
            evaluation = question.evaluation_json if isinstance(question.evaluation_json, dict) else {}
            db.session.add(QuestionReview(
                interview_question_id=question.interview_question_id,
                reviewer_id=g.user.user_id,
                rubric_version=evaluation.get("rubric_version"),
                ai_score=question.final_ai_score,
                teacher_score=question.teacher_score,
                ai_criteria_json=evaluation.get("criteria_scores"),
                teacher_criteria_json=teacher_criteria,
                teacher_remark=question.teacher_remark,
            ))
        if question.teacher_score is not None or question.teacher_remark or teacher_criteria:
            question.needs_review = False
        elif question.final_ai_score is None or (
            isinstance(question.evaluation_json, dict)
            and question.evaluation_json.get("needs_teacher_review", False)
        ):
            question.needs_review = True

    if overall_review_submitted:
        report.reviewed_at = datetime.utcnow()
    generate_interview_report(interview)
    db.session.commit()
    return jsonify(_report_payload(interview, report))


@bp.get("/interviews/<int:interview_id>/report.pdf")
@login_required()
def pdf_report(interview_id):
    interview, error = _authorized_interview(interview_id)
    if error is not None:
        return error
    if interview.status != "COMPLETED":
        return api_error("The report is available after the interview is completed.", "report_not_ready", 409)
    interview, report = _get_or_create_report(interview_id)
    questions = InterviewQuestion.query.filter_by(interview_id=interview_id).order_by(
        InterviewQuestion.question_order
    ).all()
    return send_file(build_pdf(interview, questions, report), as_attachment=True, download_name=f"queme-interview-{interview_id}.pdf", mimetype="application/pdf")


@bp.get("/interviews/<int:interview_id>/report.xlsx")
@login_required()
def excel_report(interview_id):
    interview, error = _authorized_interview(interview_id)
    if error is not None:
        return error
    if interview.status != "COMPLETED":
        return api_error("The report is available after the interview is completed.", "report_not_ready", 409)
    interview, report = _get_or_create_report(interview_id)
    questions = InterviewQuestion.query.filter_by(interview_id=interview_id).order_by(
        InterviewQuestion.question_order
    ).all()
    analytics = build_report_analytics(questions)
    rows = [
        {
            "question_order": q.question_order,
            "question": q.question.question_text if q.question else (q.followup_text or ""),
            "topics": ", ".join(q.question.topics_json or []) if q.question else "",
            "is_followup": bool(q.is_followup),
            "transcript": q.transcript or "",
            "content_score": float(q.content_score) if q.content_score is not None else "",
            "delivery_score": float(q.delivery_score) if q.delivery_score is not None else "",
            "ai_score": float(q.final_ai_score) if q.final_ai_score is not None else "",
            "teacher_score": float(q.teacher_score) if q.teacher_score is not None else "",
            "teacher_remark": q.teacher_remark or "",
            "needs_review": bool(q.needs_review),
            "feedback": (q.evaluation_json or {}).get("feedback", "") if isinstance(q.evaluation_json, dict) else "",
            "rubric_breakdown": json.dumps((q.evaluation_json or {}).get("criteria_scores", {}), ensure_ascii=False)
            if isinstance(q.evaluation_json, dict) else "",
            "criterion_feedback_and_evidence": json.dumps((q.evaluation_json or {}).get("criterion_details", {}), ensure_ascii=False)
            if isinstance(q.evaluation_json, dict) else "",
            "words_per_minute": float(q.analysis.words_per_minute) if q.analysis and q.analysis.words_per_minute is not None else "",
            "pause_count": q.analysis.pause_count if q.analysis and q.analysis.pause_count is not None else "",
            "total_pause_duration_seconds": float(q.analysis.total_pause_duration_seconds) if q.analysis and q.analysis.total_pause_duration_seconds is not None else "",
            "longest_pause_seconds": float(q.analysis.longest_pause_seconds) if q.analysis and q.analysis.longest_pause_seconds is not None else "",
            "filler_word_count": q.analysis.filler_word_count if q.analysis and q.analysis.filler_word_count is not None else "",
            "audio_quality": q.analysis.audio_quality_status if q.analysis else "",
            "analysis_status": question_analysis_status(q)["status"],
            "processing_status": answer_processing_status(q),
        }
        for q in questions
    ]
    rows.append({
        "question_order": "Overall",
        "question": interview.template.title if interview.template else "Interview",
        "transcript": "",
        "content_score": "",
        "delivery_score": "",
        "ai_score": float(report.ai_final_score) if report.ai_final_score is not None else "",
        "teacher_score": float(report.teacher_score) if report.teacher_score is not None else "",
        "teacher_remark": report.teacher_remark or "",
        "needs_review": report.report_status == "NEEDS_REVIEW",
        "feedback": f"Final score: {report.final_score}; status: {report.report_status}",
    })
    audio = analytics["audio_summary"]
    coverage = analytics["analysis_coverage"]
    summary = {
        "Overall score (0-10)": float(report.final_score) if report.final_score is not None else "Not available",
        "Speaking rate average (WPM)": {"value": audio["words_per_minute"], "count": audio["metric_sample_counts"]["words_per_minute"]},
        "Pauses average per answer": {"value": audio["pause_count"], "count": audio["metric_sample_counts"]["pause_count"]},
        "Total pause duration average (seconds)": {"value": audio["total_pause_duration_seconds"], "count": audio["metric_sample_counts"]["total_pause_duration_seconds"]},
        "Longest pause average (seconds)": {"value": audio["longest_pause_seconds"], "count": audio["metric_sample_counts"]["longest_pause_seconds"]},
        "Fillers per 100 spoken words": {"value": audio["fillers_per_100_words"], "count": audio["metric_sample_counts"]["fillers_per_100_words"]},
        "Average delivery score (0-10)": {"value": audio["delivery_score"], "count": audio["metric_sample_counts"]["delivery_score"]},
        "Filler word denominator": audio["filler_word_denominator"],
        "Total questions": coverage["total_questions"],
        "Attempted questions": coverage["attempted_questions"],
        "Questions answered": coverage["questions_answered"],
        "Usable recordings": coverage["usable_recordings"],
        "Successfully transcribed answers": coverage["transcribed_answers"],
        "Completed content evaluations": coverage["content_evaluations"],
        "Completed communication analyses": coverage["communication_analyses"],
        "Overall analysis coverage": coverage["coverage"]["overall"]["percentage"],
        "Topic analysis": json.dumps(analytics["topic_analysis"], ensure_ascii=False),
        "Improvement plan": json.dumps(analytics["improvement_plan"], ensure_ascii=False),
    }
    return send_file(build_excel(rows, title="Interview Report", summary=summary), as_attachment=True, download_name=f"queme-interview-{interview_id}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
