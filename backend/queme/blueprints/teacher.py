from datetime import datetime, timezone
import math

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError

from ..api_errors import api_error, json_object
from ..authz import login_required
from ..extensions import db
from ..models import (
    Batch,
    Interview,
    InterviewQuestion,
    InterviewTemplate,
    QuestionBank,
    Report,
    Rubric,
    TemplateQuestion,
    User,
)
from ..services.llm import generate_questions

bp = Blueprint("teacher", __name__)

QUESTION_TYPES = {"technical", "hr", "behavioral", "communication", "other"}
DIFFICULTIES = {"easy", "medium", "hard"}
MAX_TEMPLATE_QUESTIONS = 50


def _positive_id(value, field):
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        return None, f"{field} must be a positive integer."
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"{field} must be a positive integer."
    if parsed <= 0:
        return None, f"{field} must be a positive integer."
    return parsed, None


def _overall_reviewed(interview, report):
    if report is None:
        return bool((interview.teacher_remark or "").strip())
    return bool(
        report.reviewed_at
        or report.report_status == "REVIEWED"
        or report.teacher_score is not None
        or (report.teacher_remark or "").strip()
    )


def _overall_reviewed_expression():
    report_reviewed = or_(
        Report.reviewed_at.isnot(None),
        Report.report_status == "REVIEWED",
        Report.teacher_score.isnot(None),
        and_(Report.teacher_remark.isnot(None), func.trim(Report.teacher_remark) != ""),
    )
    legacy_reviewed_without_report = and_(
        Report.report_id.is_(None),
        Interview.teacher_remark.isnot(None),
        func.trim(Interview.teacher_remark) != "",
    )
    return or_(report_reviewed, legacy_reviewed_without_report)


def _can_use_questions(query):
    admins = db.session.query(User.user_id).filter(User.role == "admin")
    return query.filter(
        or_(
            QuestionBank.created_by == g.user.user_id,
            QuestionBank.created_by.is_(None),
            QuestionBank.created_by.in_(admins),
        )
    )


def _can_use_rubrics(query):
    admins = db.session.query(User.user_id).filter(User.role == "admin")
    return query.filter(
        or_(
            Rubric.created_by == g.user.user_id,
            Rubric.created_by.is_(None),
            Rubric.created_by.in_(admins),
        )
    )


def _question_input(data, existing=None, partial=False):
    values = {
        "question_text": existing.question_text if existing else None,
        "question_type": existing.question_type if existing else None,
        "difficulty": existing.difficulty if existing else None,
        "expected_key_points": existing.expected_key_points if existing else None,
        "reference_answer": existing.reference_answer if existing else None,
        "topics_json": existing.topics_json if existing else [],
        "is_active": existing.is_active if existing else True,
    }
    for key in values:
        if key in data:
            values[key] = data[key]
        elif key == "topics_json":
            values[key] = data.get("topics", values[key])
        elif not partial and existing is None and key in ("question_text", "question_type", "difficulty"):
            return None, f"{key} is required."

    text = values["question_text"]
    if not isinstance(text, str) or not text.strip() or len(text.strip()) > 5000:
        return None, "question_text must be a non-empty string of at most 5000 characters."
    values["question_text"] = text.strip()

    question_type = values["question_type"]
    if not isinstance(question_type, str) or question_type.strip().lower() not in QUESTION_TYPES:
        return None, "question_type must be technical, hr, behavioral, communication, or other."
    values["question_type"] = question_type.strip().lower()

    difficulty = values["difficulty"]
    if not isinstance(difficulty, str) or difficulty.strip().lower() not in DIFFICULTIES:
        return None, "difficulty must be easy, medium, or hard."
    values["difficulty"] = difficulty.strip().lower()

    for key, limit in (("expected_key_points", 5000), ("reference_answer", 10000)):
        value = values[key]
        if value is not None and (not isinstance(value, str) or len(value) > limit):
            return None, f"{key} must be a string of at most {limit} characters."
        if isinstance(value, str):
            values[key] = value.strip() or None
    topics = values["topics_json"]
    if isinstance(topics, str):
        topics = topics.split(",")
    if not isinstance(topics, list) or len(topics) > 20 or any(
        not isinstance(topic, str) or not topic.strip() or len(topic.strip()) > 80
        for topic in topics
    ):
        return None, "topics must be an array of up to 20 non-empty topic names of at most 80 characters."
    values["topics_json"] = list(dict.fromkeys(topic.strip() for topic in topics))
    if not isinstance(values["is_active"], bool):
        return None, "is_active must be a boolean."
    return values, None


def _rubric_criteria(value):
    if not isinstance(value, dict) or not isinstance(value.get("criteria"), list):
        return None, "criteria_json must be an object containing a criteria array."
    criteria = value["criteria"]
    if not 1 <= len(criteria) <= 20:
        return None, "criteria_json.criteria must contain between 1 and 20 criteria."
    normalized = []
    weighted = []
    names = set()
    for item in criteria:
        if isinstance(item, str):
            name = item.strip()
            if not name or len(name) > 100:
                return None, "Each rubric criterion must be a non-empty string of at most 100 characters."
            normalized.append(name)
        elif isinstance(item, dict):
            name = item.get("name")
            description = item.get("description", "")
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
                return None, "Each rubric criterion needs a name of at most 100 characters."
            if not isinstance(description, str) or len(description) > 1000:
                return None, "A rubric criterion description must be a string of at most 1000 characters."
            criterion = {"name": name.strip(), "description": description.strip()}
            if "weight" in item:
                weight = item["weight"]
                if isinstance(weight, bool):
                    return None, "Rubric criterion weights must be finite numbers from 0 to 100."
                try:
                    weight = float(weight)
                except (TypeError, ValueError):
                    return None, "Rubric criterion weights must be finite numbers from 0 to 100."
                if not math.isfinite(weight) or not 0 <= weight <= 100:
                    return None, "Rubric criterion weights must be finite numbers from 0 to 100."
                criterion["weight"] = weight
                weighted.append(weight)
            normalized.append(criterion)
        else:
            return None, "Rubric criteria must be strings or objects with name and optional description."
        criterion_name = item if isinstance(item, str) else item.get("name")
        normalized_name = criterion_name.strip().casefold()
        if normalized_name in names:
            return None, "Rubric criterion names must be unique."
        names.add(normalized_name)
    if weighted and (len(weighted) != len(normalized) or not math.isclose(sum(weighted), 100, abs_tol=1e-6)):
        return None, "Either provide no weights (equal weighting) or provide a weight for every criterion totaling 100."
    return {"criteria": normalized}, None


def _rubric_input(data, existing=None, partial=False):
    values = {
        "rubric_name": existing.rubric_name if existing else None,
        "rubric_type": existing.rubric_type if existing else None,
        "criteria_json": existing.criteria_json if existing else None,
        "maximum_score": existing.maximum_score if existing else 10,
    }
    for key in values:
        if key in data:
            values[key] = data[key]
        elif not partial and existing is None and key in ("rubric_name", "rubric_type", "criteria_json"):
            return None, f"{key} is required."

    name = values["rubric_name"]
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        return None, "rubric_name must be a non-empty string of at most 100 characters."
    values["rubric_name"] = name.strip()

    rubric_type = values["rubric_type"]
    if not isinstance(rubric_type, str) or rubric_type.strip().lower() not in QUESTION_TYPES:
        return None, "rubric_type must be technical, hr, behavioral, communication, or other."
    values["rubric_type"] = rubric_type.strip().lower()

    criteria, error = _rubric_criteria(values["criteria_json"])
    if error:
        return None, error
    values["criteria_json"] = criteria

    maximum = values["maximum_score"]
    if isinstance(maximum, bool):
        return None, "maximum_score must be an integer from 1 to 100."
    try:
        maximum = int(maximum)
    except (TypeError, ValueError):
        return None, "maximum_score must be an integer from 1 to 100."
    if maximum < 1 or maximum > 100 or str(maximum) != str(values["maximum_score"]):
        return None, "maximum_score must be an integer from 1 to 100."
    values["maximum_score"] = maximum
    return values, None


@bp.get("/questions")
@login_required("teacher")
def list_questions():
    query = _can_use_questions(QuestionBank.query)
    active_filter = request.args.get("is_active", "true").lower()
    if active_filter not in ("true", "false", "all"):
        return api_error("is_active must be true, false, or all.", "invalid_is_active", 400)
    if active_filter == "true":
        query = query.filter(QuestionBank.is_active.is_(True))
    elif active_filter == "false":
        query = query.filter(QuestionBank.is_active.is_(False))
    rows = query.order_by(QuestionBank.created_at.desc(), QuestionBank.question_id.desc()).all()
    return jsonify([row.to_dict() for row in rows])


@bp.post("/questions")
@login_required("teacher")
def create_question():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    values, error = _question_input(data)
    if error:
        return api_error(error, "invalid_question", 400)
    question = QuestionBank(created_by=g.user.user_id, **values)
    db.session.add(question)
    db.session.commit()
    return jsonify(question.to_dict()), 201


def _normalized_question_text(value):
    return " ".join(value.split()).casefold()


@bp.post("/questions/commit-drafts")
@login_required("teacher")
def commit_question_drafts():
    """Persist selected locally generated drafts once and return their reusable question IDs."""
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list) or not 1 <= len(raw_questions) <= MAX_TEMPLATE_QUESTIONS:
        return api_error("questions must contain between 1 and 50 selected drafts.", "invalid_drafts", 400)

    normalized_rows = []
    for index, item in enumerate(raw_questions):
        if not isinstance(item, dict):
            return api_error(f"questions[{index}] must be an object.", "invalid_draft", 400)
        values, error = _question_input(item)
        if error:
            return api_error(f"questions[{index}]: {error}", "invalid_draft", 400)
        values["is_active"] = True
        normalized_rows.append(values)

    # Normalize in Python so duplicate detection treats repeated whitespace and
    # case-only differences as the same teacher-owned question.
    saved_by_text = {
        _normalized_question_text(row.question_text): row
        for row in QuestionBank.query.filter_by(created_by=g.user.user_id).all()
    }
    output = []
    output_ids = []
    seen_ids = set()
    created_count = 0
    try:
        for values in normalized_rows:
            key = _normalized_question_text(values["question_text"])
            question = saved_by_text.get(key)
            if question is None:
                question = QuestionBank(created_by=g.user.user_id, **values)
                db.session.add(question)
                db.session.flush()
                saved_by_text[key] = question
                created_count += 1
            elif not question.is_active:
                question.is_active = True
            output_ids.append(question.question_id)
            if question.question_id not in seen_ids:
                output.append(question.to_dict())
                seen_ids.add(question.question_id)
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        current_app.logger.warning("Database integrity conflict operation=teacher.commit_question_drafts error_type=%s", type(exc).__name__)
        return api_error("Selected questions could not be saved because of a conflicting record.", "question_conflict", 409)
    return jsonify({"questions": output, "question_ids": output_ids, "created_count": created_count, "reused_count": len(output) - created_count}), 200


@bp.post("/questions/generate")
@login_required("teacher")
def draft_questions():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    topic = data.get("topic")
    question_type = data.get("question_type")
    difficulty = data.get("difficulty")
    if not isinstance(topic, str) or not topic.strip() or len(topic.strip()) > 200:
        return api_error("topic must be a non-empty string of at most 200 characters.", "invalid_topic", 400)
    if not isinstance(question_type, str) or question_type.strip().lower() not in QUESTION_TYPES:
        return api_error("question_type must be technical, hr, behavioral, communication, or other.", "invalid_question_type", 400)
    if not isinstance(difficulty, str) or difficulty.strip().lower() not in DIFFICULTIES:
        return api_error("difficulty must be easy, medium, or hard.", "invalid_difficulty", 400)

    result = generate_questions(topic.strip(), question_type.strip().lower(), difficulty.strip().lower(), count=10)
    drafts = []
    generated_rows = result.get("questions")
    if not isinstance(generated_rows, list):
        generated_rows = []
    for row in generated_rows[:10]:
        if not isinstance(row, dict):
            continue
        text = row.get("question_text")
        if not isinstance(text, str) or not text.strip():
            continue
        drafts.append({
            "question_text": text.strip()[:5000],
            "question_type": question_type.strip().lower(),
            "difficulty": difficulty.strip().lower(),
            "expected_key_points": row.get("expected_key_points", "")[:5000]
            if isinstance(row.get("expected_key_points", ""), str)
            else "",
        })
    available = bool(result.get("available")) and bool(drafts)
    return jsonify({
        "available": available,
        "questions": drafts if available else [],
        "manual_fallback": not available,
        "message": None if available else result.get("error") or "AI drafts are unavailable. You can still create and save questions manually.",
    })


@bp.get("/questions/<int:question_id>")
@login_required("teacher")
def get_question(question_id):
    question = _can_use_questions(QuestionBank.query).filter_by(question_id=question_id).first()
    if question is None:
        return api_error("Question not found.", "question_not_found", 404)
    return jsonify(question.to_dict())


@bp.route("/questions/<int:question_id>", methods=["PUT", "PATCH"])
@login_required("teacher")
def update_question(question_id):
    question = db.session.get(QuestionBank, question_id)
    if question is None or question.created_by != g.user.user_id:
        return api_error("Question not found.", "question_not_found", 404)
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    values, error = _question_input(data, existing=question, partial=True)
    if error:
        return api_error(error, "invalid_question", 400)
    assigned_use = InterviewQuestion.query.filter_by(question_id=question_id).first() is not None
    if assigned_use and any(
        values[key] != getattr(question, key)
        for key in ("question_text", "question_type", "difficulty", "expected_key_points", "reference_answer", "topics_json")
    ):
        return api_error("Question content cannot change after it has been used in an interview.", "question_in_use", 409)
    for key, value in values.items():
        setattr(question, key, value)
    db.session.commit()
    return jsonify(question.to_dict())


@bp.delete("/questions/<int:question_id>")
@login_required("teacher")
def delete_question(question_id):
    question = db.session.get(QuestionBank, question_id)
    if question is None or question.created_by != g.user.user_id:
        return api_error("Question not found.", "question_not_found", 404)
    if TemplateQuestion.query.filter_by(question_id=question_id).first() or InterviewQuestion.query.filter_by(question_id=question_id).first():
        return api_error("Question is used by a template or interview. Deactivate it instead of deleting it.", "question_in_use", 409)
    db.session.delete(question)
    db.session.commit()
    return "", 204


@bp.get("/rubrics")
@login_required("teacher")
def list_rubrics():
    rows = _can_use_rubrics(Rubric.query).order_by(Rubric.rubric_name, Rubric.rubric_id).all()
    return jsonify([row.to_dict() for row in rows])


@bp.post("/rubrics")
@login_required("teacher")
def create_rubric():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    values, error = _rubric_input(data)
    if error:
        return api_error(error, "invalid_rubric", 400)
    rubric = Rubric(created_by=g.user.user_id, **values)
    db.session.add(rubric)
    db.session.commit()
    return jsonify(rubric.to_dict()), 201


@bp.get("/rubrics/<int:rubric_id>")
@login_required("teacher")
def get_rubric(rubric_id):
    rubric = _can_use_rubrics(Rubric.query).filter_by(rubric_id=rubric_id).first()
    if rubric is None:
        return api_error("Rubric not found.", "rubric_not_found", 404)
    return jsonify(rubric.to_dict())


@bp.route("/rubrics/<int:rubric_id>", methods=["PUT", "PATCH"])
@login_required("teacher")
def update_rubric(rubric_id):
    rubric = db.session.get(Rubric, rubric_id)
    if rubric is None or rubric.created_by != g.user.user_id:
        return api_error("Rubric not found.", "rubric_not_found", 404)
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    values, error = _rubric_input(data, existing=rubric, partial=True)
    if error:
        return api_error(error, "invalid_rubric", 400)
    if InterviewQuestion.query.filter_by(rubric_id=rubric_id).first() and any(
        values[key] != getattr(rubric, key)
        for key in ("rubric_name", "rubric_type", "criteria_json", "maximum_score")
    ):
        return api_error("Rubric cannot change after it has been used in an interview.", "rubric_in_use", 409)
    for key, value in values.items():
        setattr(rubric, key, value)
    db.session.commit()
    return jsonify(rubric.to_dict())


@bp.delete("/rubrics/<int:rubric_id>")
@login_required("teacher")
def delete_rubric(rubric_id):
    rubric = db.session.get(Rubric, rubric_id)
    if rubric is None or rubric.created_by != g.user.user_id:
        return api_error("Rubric not found.", "rubric_not_found", 404)
    if TemplateQuestion.query.filter_by(rubric_id=rubric_id).first() or InterviewQuestion.query.filter_by(rubric_id=rubric_id).first():
        return api_error("Rubric is used by a template or interview and cannot be deleted.", "rubric_in_use", 409)
    db.session.delete(rubric)
    db.session.commit()
    return "", 204


def _template_question_rows(raw_questions):
    if not isinstance(raw_questions, list) or not 1 <= len(raw_questions) <= MAX_TEMPLATE_QUESTIONS:
        return None, "questions must be an array with 1 to 50 entries."
    question_ids = []
    rubric_ids = []
    normalized = []
    for index, item in enumerate(raw_questions):
        if not isinstance(item, dict):
            return None, f"questions[{index}] must be an object."
        question_id, error = _positive_id(item.get("question_id"), f"questions[{index}].question_id")
        if error:
            return None, error
        rubric_id = None
        if item.get("rubric_id") is not None:
            rubric_id, error = _positive_id(item.get("rubric_id"), f"questions[{index}].rubric_id")
            if error:
                return None, error
            rubric_ids.append(rubric_id)
        question_ids.append(question_id)
        normalized.append({"question_id": question_id, "rubric_id": rubric_id, "question_order": index + 1})

    if len(set(question_ids)) != len(question_ids):
        return None, "A template cannot contain the same question more than once."
    questions = _can_use_questions(QuestionBank.query).filter(
        QuestionBank.question_id.in_(question_ids), QuestionBank.is_active.is_(True)
    ).all()
    if len(questions) != len(question_ids):
        return None, "One or more questions are unavailable or inactive."
    if rubric_ids:
        rubrics = _can_use_rubrics(Rubric.query).filter(Rubric.rubric_id.in_(rubric_ids)).all()
        if len({row.rubric_id for row in rubrics}) != len(set(rubric_ids)):
            return None, "One or more rubrics are unavailable."
    return normalized, None


def _template_input(data, existing=None, partial=False):
    title = data.get("title", existing.title if existing else None)
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 150:
        return None, "title must be a non-empty string of at most 150 characters."
    description = data.get("description", existing.description if existing else None)
    if description is not None and (not isinstance(description, str) or len(description) > 5000):
        return None, "description must be a string of at most 5000 characters."
    duration = data.get("duration_minutes", existing.duration_minutes if existing else None)
    if duration is not None:
        if isinstance(duration, bool):
            return None, "duration_minutes must be an integer from 1 to 600."
        try:
            parsed_duration = int(duration)
        except (TypeError, ValueError):
            return None, "duration_minutes must be an integer from 1 to 600."
        if parsed_duration < 1 or parsed_duration > 600 or str(parsed_duration) != str(duration):
            return None, "duration_minutes must be an integer from 1 to 600."
        duration = parsed_duration
    questions = None
    if "questions" in data:
        questions, error = _template_question_rows(data["questions"])
        if error:
            return None, error
    elif existing is None or not partial:
        return None, "questions is required."
    return {"title": title.strip(), "description": description, "duration_minutes": duration, "questions": questions}, None


def _replace_template_questions(template, rows):
    if rows is None:
        return
    template.questions.clear()
    for row in rows:
        template.questions.append(TemplateQuestion(**row))


@bp.get("/templates")
@login_required("teacher")
def list_templates():
    rows = InterviewTemplate.query.filter_by(created_by=g.user.user_id).order_by(
        InterviewTemplate.created_at.desc(), InterviewTemplate.template_id.desc()
    ).all()
    return jsonify([row.to_dict(include_questions=True) for row in rows])


@bp.post("/templates")
@login_required("teacher")
def create_template():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    values, error = _template_input(data)
    if error:
        return api_error(error, "invalid_template", 400)
    question_rows = values.pop("questions")
    template = InterviewTemplate(created_by=g.user.user_id, **values)
    _replace_template_questions(template, question_rows)
    db.session.add(template)
    db.session.commit()
    return jsonify(template.to_dict(include_questions=True)), 201


@bp.get("/templates/<int:template_id>")
@login_required("teacher")
def get_template(template_id):
    template = InterviewTemplate.query.filter_by(
        template_id=template_id, created_by=g.user.user_id
    ).first()
    if template is None:
        return api_error("Template not found.", "template_not_found", 404)
    return jsonify(template.to_dict(include_questions=True))


@bp.route("/templates/<int:template_id>", methods=["PUT", "PATCH"])
@login_required("teacher")
def update_template(template_id):
    template = db.session.get(InterviewTemplate, template_id)
    if template is None or template.created_by != g.user.user_id:
        return api_error("Template not found.", "template_not_found", 404)
    if Interview.query.filter_by(template_id=template_id).first():
        return api_error("Template has assigned interviews and can no longer be changed.", "template_in_use", 409)
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    values, error = _template_input(data, existing=template, partial=True)
    if error:
        return api_error(error, "invalid_template", 400)
    question_rows = values.pop("questions")
    for key, value in values.items():
        setattr(template, key, value)
    _replace_template_questions(template, question_rows)
    db.session.commit()
    return jsonify(template.to_dict(include_questions=True))


@bp.delete("/templates/<int:template_id>")
@login_required("teacher")
def delete_template(template_id):
    template = db.session.get(InterviewTemplate, template_id)
    if template is None or template.created_by != g.user.user_id:
        return api_error("Template not found.", "template_not_found", 404)
    if Interview.query.filter_by(template_id=template_id).first():
        return api_error("Template has assigned interviews and cannot be deleted.", "template_in_use", 409)
    TemplateQuestion.query.filter_by(template_id=template_id).delete(synchronize_session=False)
    db.session.delete(template)
    db.session.commit()
    return "", 204


def _scheduled_at(value):
    if value is None or value == "":
        return None, None
    if not isinstance(value, str):
        return None, "scheduled_at must be an ISO-8601 date/time string."
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, "scheduled_at must be an ISO-8601 date/time string."
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed, None


@bp.get("/interviews")
@login_required("teacher", "student")
def list_assigned_interviews():
    owner_key = "teacher_id" if g.user.role == "teacher" else "student_id"
    rows = db.session.query(Interview, Report).outerjoin(
        Report, Report.interview_id == Interview.interview_id
    ).filter(getattr(Interview, owner_key) == g.user.user_id).order_by(
        Interview.created_at.desc(), Interview.interview_id.desc()
    ).all()
    return jsonify([
        {
            **interview.to_dict(),
            "report_status": report.report_status if report else None,
            "report_reviewed_at": report.reviewed_at.isoformat() if report and report.reviewed_at else None,
            "teacher_review_status": (
                "REVIEWED" if _overall_reviewed(interview, report) else "PENDING"
            ) if interview.status == "COMPLETED" else None,
        }
        for interview, report in rows
    ])


@bp.get("/teacher/analytics")
@login_required("teacher")
def teacher_analytics():
    rows = Interview.query.filter_by(teacher_id=g.user.user_id).all()
    pending_reviews = db.session.query(func.count(Interview.interview_id)).outerjoin(
        Report, Report.interview_id == Interview.interview_id
    ).filter(
        Interview.teacher_id == g.user.user_id,
        Interview.status == "COMPLETED",
        ~_overall_reviewed_expression(),
    ).scalar() or 0
    scored = [
        float(row.final_score)
        for row in rows
        if row.status == "COMPLETED" and row.final_score is not None
    ]
    return jsonify({
        "interview_count": len(rows),
        "active_interviews": sum(row.status in ("SCHEDULED", "IN_PROGRESS") for row in rows),
        "completed_interviews": sum(row.status == "COMPLETED" for row in rows),
        "students_assigned": len({row.student_id for row in rows}),
        "pending_reviews": pending_reviews,
        "average_score": round(sum(scored) / len(scored), 2) if scored else None,
    })


@bp.get("/teacher/students")
@login_required("teacher")
def teacher_students():
    batch_id, error = _positive_id(request.args.get("batch_id"), "batch_id")
    if error:
        return api_error(error, "invalid_batch_id", 400)
    batch = db.session.get(Batch, batch_id)
    if batch is None:
        return api_error("Class group not found.", "class_group_not_found", 404)
    students = User.query.filter_by(
        batch_id=batch_id, department_id=batch.department_id, role="student", account_status="ACTIVE"
    ).order_by(User.full_name, User.user_id).all()
    assigned = {
        student_id: count for student_id, count in db.session.query(Interview.student_id, func.count(Interview.interview_id))
        .filter(Interview.teacher_id == g.user.user_id, Interview.student_id.in_([row.user_id for row in students]))
        .group_by(Interview.student_id).all()
    } if students else {}
    return jsonify([{**student.to_public(), "teacher_interview_count": assigned.get(student.user_id, 0)} for student in students])


@bp.post("/interviews")
@login_required("teacher")
def assign_interviews():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    template_id, error = _positive_id(data.get("template_id"), "template_id")
    if error:
        return api_error(error, "invalid_template_id", 400)
    template = InterviewTemplate.query.filter_by(
        template_id=template_id, created_by=g.user.user_id
    ).first()
    if template is None:
        return api_error("Template not found.", "template_not_found", 404)
    if not template.questions:
        return api_error("Template must contain at least one question before assignment.", "empty_template", 400)

    has_student = "student_id" in data
    has_batch = "batch_id" in data
    if has_student == has_batch:
        return api_error("Provide exactly one of student_id or batch_id.", "invalid_assignment_target", 400)
    scheduled_at, error = _scheduled_at(data.get("scheduled_at"))
    if error:
        return api_error(error, "invalid_schedule", 400)

    if has_student:
        student_id, error = _positive_id(data["student_id"], "student_id")
        if error:
            return api_error(error, "invalid_student_id", 400)
        students = User.query.filter_by(user_id=student_id, role="student", account_status="ACTIVE").all()
        if not students:
            return api_error("student_id must identify an active student.", "student_not_found", 404)
    else:
        batch_id, error = _positive_id(data["batch_id"], "batch_id")
        if error:
            return api_error(error, "invalid_batch_id", 400)
        if db.session.get(Batch, batch_id) is None:
            return api_error("batch_id does not identify an existing batch.", "batch_not_found", 404)
        students = User.query.filter_by(batch_id=batch_id, role="student", account_status="ACTIVE").order_by(User.user_id).all()
        if not students:
            return api_error("The batch has no active students to assign.", "empty_batch", 409)

    interviews = []
    try:
        for student in students:
            interview = Interview(
                student_id=student.user_id,
                teacher_id=g.user.user_id,
                template_id=template.template_id,
                scheduled_at=scheduled_at,
                status="SCHEDULED",
                consent_given=False,
                current_index=0,
            )
            for item in template.questions:
                interview.questions.append(InterviewQuestion(
                    question_id=item.question_id,
                    rubric_id=item.rubric_id,
                    question_order=item.question_order,
                    is_followup=False,
                ))
            db.session.add(interview)
            interviews.append(interview)
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        current_app.logger.warning("Database integrity conflict operation=teacher.assign_interviews error_type=%s", type(exc).__name__)
        return api_error("The interviews could not be assigned because related data changed.", "assignment_conflict", 409)
    return jsonify({
        "assigned_count": len(interviews),
        "interviews": [row.to_dict(include_questions=True) for row in interviews],
    }), 201


@bp.post("/interviews/<int:interview_id>/cancel")
@login_required("teacher")
def cancel_scheduled_interview(interview_id):
    interview = Interview.query.filter_by(interview_id=interview_id, teacher_id=g.user.user_id).first()
    if interview is None:
        return api_error("Interview not found.", "interview_not_found", 404)
    if interview.status != "SCHEDULED":
        return api_error("Only scheduled interviews can be cancelled.", "invalid_interview_state", 409)
    interview.status = "CANCELLED"
    db.session.commit()
    return jsonify(interview.to_dict())
