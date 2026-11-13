import math
from statistics import correlation, mean, StatisticsError

from flask import Blueprint, current_app, jsonify, request, send_file
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..api_errors import api_error, json_object
from ..authz import login_required
from ..academics import COURSES, SEMESTERS
from ..extensions import db
from ..models import Batch, Department, Interview, InterviewQuestion, QuestionReview, Report, SystemSetting, User
from ..services.reports import build_excel

bp = Blueprint("admin", __name__)


def _name(data, field, max_length):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        return None, f"{field} is required."
    value = value.strip()
    if len(value) > max_length:
        return None, f"{field} must be {max_length} characters or fewer."
    return value, None


def _positive_id(value, field):
    if isinstance(value, bool):
        return None, f"{field} must be a positive integer."
    if isinstance(value, float) and not value.is_integer():
        return None, f"{field} must be a positive integer."
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"{field} must be a positive integer."
    if parsed <= 0:
        return None, f"{field} must be a positive integer."
    return parsed, None


def _department_dict(department):
    return {"department_id": department.department_id, "department_name": department.department_name,
            "course_id": department.department_id, "course_name": department.department_name}


def _batch_dict(batch):
    course = db.session.get(Department, batch.department_id)
    return {
        "batch_id": batch.batch_id,
        "department_id": batch.department_id,
        "batch_name": batch.batch_name,
        "academic_year": batch.academic_year,
        "course_id": batch.department_id,
        "semester": batch.batch_name,
        "course_name": course.department_name if course else None,
    }


@bp.get("/pending-users")
@login_required("admin")
def pending_users():
    rows = User.query.filter_by(account_status="PENDING").order_by(User.created_at.desc()).all()
    return jsonify([user.to_public() for user in rows])


@bp.get("/users")
@login_required("admin")
def users():
    query = User.query
    role = request.args.get("role")
    status = request.args.get("account_status")
    if role:
        role = role.strip().lower()
        if role not in ("student", "teacher", "admin"):
            return api_error("role must be student, teacher, or admin.", "invalid_role", 400)
        query = query.filter_by(role=role)
    if status:
        status = status.strip().upper()
        if status not in ("PENDING", "ACTIVE", "REJECTED"):
            return api_error("account_status must be PENDING, ACTIVE, or REJECTED.", "invalid_account_status", 400)
        query = query.filter_by(account_status=status)
    rows = query.order_by(User.created_at.desc(), User.user_id.desc()).all()
    return jsonify([user.to_public() for user in rows])


@bp.post("/users/<int:user_id>/status")
@login_required("admin")
def set_status(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return api_error("User not found.", "user_not_found", 404)
    if user.role == "admin":
        return api_error("Admin accounts cannot be changed through registration approval.", "admin_status_protected", 403)

    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    status = data.get("account_status")
    if not isinstance(status, str) or status.strip().upper() not in ("ACTIVE", "REJECTED"):
        return api_error("account_status must be ACTIVE or REJECTED.", "invalid_account_status", 400)
    user.account_status = status.strip().upper()
    db.session.commit()
    return jsonify(user.to_public())


# These read-only lists are public so the registration form can populate its
# department and cohort selectors before a student or teacher has an account.
@bp.get("/departments")
@bp.get("/courses")
def list_departments():
    rows = Department.query.filter(func.upper(Department.department_name).in_(COURSES)).order_by(Department.department_name).all()
    return jsonify([_department_dict(row) for row in rows])


@bp.post("/departments")
@login_required("admin")
def create_department():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    name, error = _name(data, "department_name", 100)
    if error:
        return api_error(error, "invalid_department", 400)
    if Department.query.filter(func.lower(Department.department_name) == name.lower()).first():
        return api_error("Department already exists.", "department_conflict", 409)

    department = Department(department_name=name)
    db.session.add(department)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        current_app.logger.warning("Database integrity conflict operation=admin.create_department error_type=%s", type(exc).__name__)
        return api_error("Department already exists.", "department_conflict", 409)
    return jsonify(_department_dict(department)), 201


@bp.route("/departments/<int:department_id>", methods=["PUT", "PATCH"])
@login_required("admin")
def update_department(department_id):
    department = db.session.get(Department, department_id)
    if department is None:
        return api_error("Department not found.", "department_not_found", 404)
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    name, error = _name(data, "department_name", 100)
    if error:
        return api_error(error, "invalid_department", 400)
    duplicate = Department.query.filter(
        func.lower(Department.department_name) == name.lower(),
        Department.department_id != department_id,
    ).first()
    if duplicate:
        return api_error("Department already exists.", "department_conflict", 409)
    department.department_name = name
    db.session.commit()
    return jsonify(_department_dict(department))


@bp.delete("/departments/<int:department_id>")
@login_required("admin")
def delete_department(department_id):
    department = db.session.get(Department, department_id)
    if department is None:
        return api_error("Department not found.", "department_not_found", 404)
    if Batch.query.filter_by(department_id=department_id).first() or User.query.filter_by(department_id=department_id).first():
        return api_error("Department is in use by a batch or user and cannot be deleted.", "department_in_use", 409)
    db.session.delete(department)
    db.session.commit()
    return "", 204


@bp.get("/batches")
@bp.get("/semesters")
def list_batches():
    rows = Batch.query.filter(Batch.batch_name.in_(SEMESTERS)).order_by(Batch.department_id, Batch.batch_name, Batch.academic_year).all()
    return jsonify([_batch_dict(row) for row in rows])


def _batch_duplicate(department_id, name, academic_year, exclude_id=None):
    query = Batch.query.filter(
        Batch.department_id == department_id,
        func.lower(Batch.batch_name) == name.lower(),
    )
    query = query.filter(Batch.academic_year.is_(None)) if academic_year is None else query.filter_by(academic_year=academic_year)
    if exclude_id is not None:
        query = query.filter(Batch.batch_id != exclude_id)
    return query.first() is not None


@bp.post("/batches")
@bp.post("/semesters")
@login_required("admin")
def create_batch():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    department_id, error = _positive_id(data.get("course_id", data.get("department_id")), "course_id")
    if error:
        return api_error(error, "invalid_department_id", 400)
    if db.session.get(Department, department_id) is None:
        return api_error("department_id does not identify an existing department.", "department_not_found", 400)
    course = db.session.get(Department, department_id)
    if course.department_name.upper() not in COURSES:
        return api_error("Choose one of the supported courses: BCA, MCA, BSC IT.", "invalid_course", 400)
    name = data.get("semester", data.get("batch_name"))
    if not isinstance(name, str) or name.strip() not in SEMESTERS:
        return api_error("semester must be one of 1st through 8th.", "invalid_semester", 400)
    name = name.strip()
    academic_year = data.get("academic_year")
    if academic_year is not None:
        if not isinstance(academic_year, str) or len(academic_year.strip()) > 20:
            return api_error("academic_year must be a string of at most 20 characters.", "invalid_academic_year", 400)
        academic_year = academic_year.strip() or None
    if not academic_year:
        return api_error("academic_year is required to create a class group.", "missing_academic_year", 400)
    if _batch_duplicate(department_id, name, academic_year):
        return api_error("A batch with this name and academic year already exists in the department.", "batch_conflict", 409)

    batch = Batch(department_id=department_id, batch_name=name, academic_year=academic_year)
    db.session.add(batch)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        current_app.logger.warning("Database integrity conflict operation=admin.create_batch error_type=%s", type(exc).__name__)
        return api_error("Could not create batch because of a conflicting record.", "batch_conflict", 409)
    return jsonify(_batch_dict(batch)), 201


@bp.route("/batches/<int:batch_id>", methods=["PUT", "PATCH"])
@login_required("admin")
def update_batch(batch_id):
    batch = db.session.get(Batch, batch_id)
    if batch is None:
        return api_error("Batch not found.", "batch_not_found", 404)
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)

    department_id = batch.department_id
    if "department_id" in data:
        department_id, error = _positive_id(data["department_id"], "department_id")
        if error:
            return api_error(error, "invalid_department_id", 400)
        if db.session.get(Department, department_id) is None:
            return api_error("department_id does not identify an existing department.", "department_not_found", 400)
    name = batch.batch_name
    if "batch_name" in data:
        name, error = _name(data, "batch_name", 100)
        if error:
            return api_error(error, "invalid_batch", 400)
    academic_year = batch.academic_year
    if "academic_year" in data:
        academic_year = data["academic_year"]
        if academic_year is not None:
            if not isinstance(academic_year, str) or len(academic_year.strip()) > 20:
                return api_error("academic_year must be a string of at most 20 characters.", "invalid_academic_year", 400)
            academic_year = academic_year.strip() or None

    if _batch_duplicate(department_id, name, academic_year, exclude_id=batch_id):
        return api_error("A batch with this name and academic year already exists in the department.", "batch_conflict", 409)
    if User.query.filter_by(batch_id=batch_id).filter(
        db.or_(User.department_id.is_(None), User.department_id != department_id)
    ).first():
        return api_error("Cannot move a batch while its users belong to a different department.", "batch_in_use", 409)
    batch.department_id = department_id
    batch.batch_name = name
    batch.academic_year = academic_year
    db.session.commit()
    return jsonify(_batch_dict(batch))


@bp.delete("/batches/<int:batch_id>")
@login_required("admin")
def delete_batch(batch_id):
    batch = db.session.get(Batch, batch_id)
    if batch is None:
        return api_error("Batch not found.", "batch_not_found", 404)
    if User.query.filter_by(batch_id=batch_id).first():
        return api_error("Batch is assigned to users and cannot be deleted.", "batch_in_use", 409)
    db.session.delete(batch)
    db.session.commit()
    return "", 204


@bp.get("/settings")
@login_required("admin")
def get_settings():
    content = db.session.get(SystemSetting, "content_weight")
    delivery = db.session.get(SystemSetting, "delivery_weight")
    return jsonify({
        "content_weight": float(content.value) if content else 0.70,
        "delivery_weight": float(delivery.value) if delivery else 0.30,
    })


@bp.patch("/settings")
@bp.post("/settings")
@login_required("admin")
def save_settings():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    allowed = {"content_weight", "delivery_weight"}
    if not data or set(data) - allowed:
        return api_error("Provide content_weight and/or delivery_weight only.", "invalid_settings", 400)

    current_content = db.session.get(SystemSetting, "content_weight")
    current_delivery = db.session.get(SystemSetting, "delivery_weight")
    values = {
        "content_weight": float(current_content.value) if current_content else 0.70,
        "delivery_weight": float(current_delivery.value) if current_delivery else 0.30,
    }
    for key, value in data.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return api_error(f"{key} must be a finite number from 0 to 1.", "invalid_weight", 400)
        try:
            parsed_value = float(value)
        except (OverflowError, ValueError):
            return api_error(f"{key} must be a finite number from 0 to 1.", "invalid_weight", 400)
        if not math.isfinite(parsed_value) or not 0 <= parsed_value <= 1:
            return api_error(f"{key} must be a finite number from 0 to 1.", "invalid_weight", 400)
        values[key] = parsed_value
    if not math.isclose(sum(values.values()), 1.0, rel_tol=0.0, abs_tol=0.000001):
        return api_error("content_weight and delivery_weight must sum to 1.0.", "invalid_weight_total", 400)

    for key, value in values.items():
        setting = db.session.get(SystemSetting, key)
        if setting is None:
            setting = SystemSetting(key=key, value=str(value))
            db.session.add(setting)
        else:
            setting.value = str(value)
    db.session.commit()
    return jsonify(values)


@bp.get("/analytics")
@login_required("admin")
def analytics():
    interview_count = Interview.query.count()
    completed = Interview.query.filter_by(status="COMPLETED").count()
    avg = db.session.query(func.avg(Interview.final_score)).filter(
        Interview.status == "COMPLETED",
        Interview.final_score.isnot(None),
    ).scalar()
    pending = User.query.filter_by(account_status="PENDING").count()
    students = User.query.filter_by(role="student", account_status="ACTIVE").count()
    teachers = User.query.filter_by(role="teacher", account_status="ACTIVE").count()
    reports_needing_review = Report.query.filter_by(report_status="NEEDS_REVIEW").count()
    return jsonify({
        "interview_count": interview_count,
        "completed_interviews": completed,
        "average_score": round(float(avg), 2) if avg is not None else None,
        "pending_accounts": pending,
        "active_students": students,
        "active_teachers": teachers,
        "reports_needing_review": reports_needing_review,
    })


@bp.get("/reports.xlsx")
@login_required("admin")
def excel_reports():
    reports = Report.query.order_by(Report.generated_at.desc()).all()
    rows = []
    for report in reports:
        interview = report.interview
        rows.append({
            "report_id": report.report_id,
            "interview_id": report.interview_id,
            "student": interview.student.full_name if interview and interview.student else "",
            "teacher": interview.teacher.full_name if interview and interview.teacher else "",
            "ai_final_score": float(report.ai_final_score) if report.ai_final_score is not None else "",
            "teacher_score": float(report.teacher_score) if report.teacher_score is not None else "",
            "final_score": float(report.final_score) if report.final_score is not None else "",
            "score_source": report.score_source,
            "report_status": report.report_status,
            "teacher_remark": report.teacher_remark or "",
            "generated_at": report.generated_at.isoformat() if report.generated_at else "",
        })
    buf = build_excel(rows or [{"report_id": "", "message": "No reports yet"}])
    return send_file(
        buf,
        as_attachment=True,
        download_name="queme-reports.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp.get("/reports")
@login_required("admin")
def reports():
    rows = Report.query.order_by(Report.generated_at.desc(), Report.report_id.desc()).limit(100).all()
    return jsonify([
        {
            **report.to_dict(),
            "student_name": report.interview.student.full_name
            if report.interview and report.interview.student else None,
            "teacher_name": report.interview.teacher.full_name
            if report.interview and report.interview.teacher else None,
            "template_title": report.interview.template.title
            if report.interview and report.interview.template else None,
        }
        for report in rows
    ])


def _validation_dataset():
    all_reviews = QuestionReview.query.order_by(QuestionReview.reviewed_at, QuestionReview.review_id).all()
    latest_by_question = {}
    for review in all_reviews:
        if review.teacher_score is not None or review.teacher_criteria_json:
            latest_by_question[review.interview_question_id] = review
    rows = []
    for review in latest_by_question.values():
        question = db.session.get(InterviewQuestion, review.interview_question_id)
        if question is None:
            continue
        rows.append({
            "interview_question_id": review.interview_question_id,
            "question": question.question.question_text if question.question else question.followup_text or "",
            "transcript": question.transcript or "",
            "ai_score": float(review.ai_score) if review.ai_score is not None else None,
            "human_reference_score": float(review.teacher_score) if review.teacher_score is not None else None,
            "rubric_version": review.rubric_version or "legacy-unknown",
            "reviewer": review.reviewer.full_name if review.reviewer else "Unknown reviewer",
            "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
            "ai_criteria_scores": review.ai_criteria_json or {},
            "human_criteria_scores": review.teacher_criteria_json or {},
        })
    return sorted(rows, key=lambda item: (item["rubric_version"], item["interview_question_id"]))


def _validation_metrics(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row["rubric_version"], []).append(row)
    output = []
    for rubric_version, samples in sorted(groups.items()):
        score_pairs = [sample for sample in samples if sample["ai_score"] is not None and sample["human_reference_score"] is not None]
        errors = [sample["ai_score"] - sample["human_reference_score"] for sample in score_pairs]
        criterion_errors = {}
        for sample in samples:
            ai_criteria = sample["ai_criteria_scores"]
            human_criteria = sample["human_criteria_scores"]
            if not isinstance(ai_criteria, dict) or not isinstance(human_criteria, dict):
                continue
            for name in ai_criteria.keys() & human_criteria.keys():
                try:
                    ai_value, human_value = float(ai_criteria[name]), float(human_criteria[name])
                except (TypeError, ValueError):
                    continue
                if math.isfinite(ai_value) and math.isfinite(human_value) and 0 <= ai_value <= 10 and 0 <= human_value <= 10:
                    criterion_errors.setdefault(name, []).append(ai_value - human_value)
        try:
            score_correlation = correlation(
                [sample["ai_score"] for sample in score_pairs],
                [sample["human_reference_score"] for sample in score_pairs],
            ) if len(score_pairs) >= 3 else None
        except StatisticsError:
            score_correlation = None
        output.append({
            "rubric_version": rubric_version,
            "reviewed_sample_count": len(samples),
            "sample_count": len(score_pairs),
            "mae": round(mean(abs(error) for error in errors), 3) if errors else None,
            "rmse": round(math.sqrt(mean(error * error for error in errors)), 3) if errors else None,
            "correlation": round(score_correlation, 3) if score_correlation is not None else None,
            "correlation_status": "AVAILABLE" if score_correlation is not None else "Need at least 3 varied score pairs.",
            "criterion_sample_count": sum(bool(sample["ai_criteria_scores"] and sample["human_criteria_scores"]) for sample in samples),
            "criterion_agreement": {
                name: {
                    "sample_count": len(values),
                    "mae": round(mean(abs(value) for value in values), 3),
                }
                for name, values in criterion_errors.items()
            },
        })
    return output


@bp.get("/validation")
@login_required("admin")
def validation_metrics():
    rows = _validation_dataset()
    return jsonify({
        "status": "AVAILABLE" if rows else "NOT_AVAILABLE",
        "message": None if rows else "Validation data not available yet.",
        "sample_count": len(rows),
        "by_rubric_version": _validation_metrics(rows),
        "dataset": rows,
    })


@bp.get("/validation.xlsx")
@login_required("admin")
def validation_export():
    rows = _validation_dataset()
    payload = rows or [{"status": "Validation data not available yet."}]
    summary = {}
    for index, metric in enumerate(_validation_metrics(rows), 1):
        summary[f"Rubric {index} · {metric['rubric_version']}"] = (
            f"n={metric['sample_count']}; MAE={metric['mae']}; RMSE={metric['rmse']}; "
            f"correlation={metric['correlation'] if metric['correlation'] is not None else metric['correlation_status']}"
        )
    workbook = build_excel(payload, title="Validation Dataset", summary=summary or {"status": "Validation data not available yet."})
    return send_file(
        workbook,
        as_attachment=True,
        download_name="queme-validation-dataset.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
