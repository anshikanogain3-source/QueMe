import re
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from flask import Blueprint, current_app, g, jsonify
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError

from ..api_errors import api_error, json_object
from ..authz import check_password, hash_password, login_required, make_token
from ..extensions import db
from ..models import Batch, Department, User
from ..academics import COURSES, SEMESTERS

bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
RESET_SALT = "password-reset"


def _send_reset_email(email, token):
    host = current_app.config.get("SMTP_HOST")
    sender = current_app.config.get("SMTP_FROM")
    if not host or not sender:
        raise RuntimeError("Password reset email is not configured.")
    reset_url = f"{current_app.config['FRONTEND_ORIGIN'].rstrip('/')}/reset-password?token={quote(token)}"
    message = EmailMessage()
    message["Subject"] = "Reset your QueMe password"
    message["From"] = sender
    message["To"] = email
    message.set_content(f"Use this link within 30 minutes to reset your QueMe password:\n\n{reset_url}\n\nIf you did not request this, you can ignore this email.")
    port = current_app.config.get("SMTP_PORT", 587)
    smtp_class = smtplib.SMTP_SSL if current_app.config.get("SMTP_USE_SSL") else smtplib.SMTP
    with smtp_class(host, port, timeout=10) as smtp:
        if not current_app.config.get("SMTP_USE_SSL"):
            smtp.starttls()
        username = current_app.config.get("SMTP_USERNAME")
        if username:
            smtp.login(username, current_app.config.get("SMTP_PASSWORD", ""))
        smtp.send_message(message)


def _optional_id(data, key):
    value = data.get(key)
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        return None, f"{key} must be a positive integer."
    if isinstance(value, float) and not value.is_integer():
        return None, f"{key} must be a positive integer."
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None, f"{key} must be a positive integer."
    if value <= 0:
        return None, f"{key} must be a positive integer."
    return value, None


@bp.post("/register")
def register():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)

    full_name = data.get("full_name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role")
    if not all(isinstance(value, str) and value.strip() for value in (full_name, email, password, role)):
        return api_error("full_name, email, password, and role are required.", "missing_fields", 400)

    full_name = full_name.strip()
    email = email.strip().lower()
    role = role.strip().lower()
    if len(full_name) > 100:
        return api_error("full_name must be 100 characters or fewer.", "invalid_full_name", 400)
    if len(email) > 150 or not EMAIL_RE.fullmatch(email):
        return api_error("Provide a valid email address (maximum 150 characters).", "invalid_email", 400)
    if role not in ("student", "teacher"):
        return api_error("role must be either 'student' or 'teacher'.", "invalid_role", 400)
    if len(password) < 12 or len(password.encode("utf-8")) > 72:
        return api_error("password must be at least 12 characters and no more than 72 UTF-8 bytes.", "invalid_password", 400)

    has_class_fields = any(key in data for key in ("course_id", "semester", "academic_year"))
    department_id, error = _optional_id(data, "course_id" if "course_id" in data else "department_id")
    if error:
        return api_error(error, "invalid_department_id", 400)
    batch_id, error = _optional_id(data, "batch_id")
    if error:
        return api_error(error, "invalid_batch_id", 400)
    if has_class_fields:
        semester = data.get("semester")
        academic_year = data.get("academic_year")
        if department_id is None or not isinstance(semester, str) or semester not in SEMESTERS or not isinstance(academic_year, str) or not academic_year.strip() or len(academic_year.strip()) > 20:
            return api_error("Choose a course, semester, and academic year to join a class group.", "invalid_class_group", 400)
        department = db.session.get(Department, department_id)
        if department is None or department.department_name.upper() not in COURSES:
            return api_error("Choose a supported course.", "invalid_course", 400)
        cohort = Batch.query.filter_by(department_id=department_id, batch_name=semester, academic_year=academic_year.strip()).first()
        if cohort is None:
            return api_error("That class group is not set up yet. Contact your administrator.", "class_group_not_found", 400)
        batch_id = cohort.batch_id
    elif department_id is not None and db.session.get(Department, department_id) is None:
        return api_error("course_id does not identify an existing course.", "course_not_found", 400)
    if batch_id is not None and not has_class_fields:
        batch = db.session.get(Batch, batch_id)
        if batch is None:
            return api_error("batch_id does not identify an existing batch.", "batch_not_found", 400)
        if department_id is not None and batch.department_id != department_id:
            return api_error("batch_id does not belong to department_id.", "batch_department_mismatch", 400)
        department_id = department_id or batch.department_id

    for key, max_length in (("roll_number", 30), ("employee_id", 30)):
        value = data.get(key)
        if value is not None and (not isinstance(value, str) or len(value.strip()) > max_length):
            return api_error(f"{key} must be a string of at most {max_length} characters.", f"invalid_{key}", 400)

    if User.query.filter_by(email=email).first():
        return api_error("Email already registered.", "email_conflict", 409)

    user = User(
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        account_status="PENDING",
        department_id=department_id,
        batch_id=batch_id,
        roll_number=(data.get("roll_number") or "").strip() or None,
        employee_id=(data.get("employee_id") or "").strip() or None,
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        current_app.logger.warning("Database integrity conflict operation=auth.register error_type=%s", type(exc).__name__)
        return api_error("Email already registered.", "email_conflict", 409)
    return jsonify({"message": "Registration submitted. Wait for admin approval.", "user": user.to_public()}), 201


@bp.post("/login")
def login():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    email = data.get("email")
    password = data.get("password")
    if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password:
        return api_error("email and password are required.", "missing_fields", 400)

    user = User.query.filter_by(email=email.strip().lower()).first()
    if not user or not check_password(password, user.password_hash):
        return api_error("Invalid email or password.", "invalid_credentials", 401)
    if user.account_status != "ACTIVE":
        return jsonify({
            "error": "Login blocked until an administrator approves this account.",
            "code": "account_not_active",
            "account_status": user.account_status,
        }), 403
    return jsonify({"token": make_token(user), "user": user.to_public()})


@bp.post("/forgot-password")
def forgot_password():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    email = data.get("email")
    if not isinstance(email, str) or not EMAIL_RE.fullmatch(email.strip()):
        return api_error("Provide a valid email address.", "invalid_email", 400)

    user = User.query.filter_by(email=email.strip().lower()).first()
    if user:
        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=RESET_SALT)
        token = serializer.dumps(user.email)
        try:
            _send_reset_email(user.email, token)
        except (OSError, smtplib.SMTPException, RuntimeError):
            current_app.logger.exception("Password reset email could not be sent.")
    return jsonify({"message": "If an account exists for that email, a password reset link has been sent."})


@bp.post("/reset-password")
def reset_password():
    data = json_object()
    if data is None:
        return api_error("Request body must be a JSON object.", "invalid_json", 400)
    token = data.get("token")
    password = data.get("password")
    if not isinstance(token, str) or not token or not isinstance(password, str):
        return api_error("token and password are required.", "missing_fields", 400)
    if len(password) < 12 or len(password.encode("utf-8")) > 72:
        return api_error("password must be at least 12 characters and no more than 72 UTF-8 bytes.", "invalid_password", 400)
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=RESET_SALT)
    try:
        email = serializer.loads(token, max_age=1800)
    except (BadSignature, SignatureExpired):
        return api_error("This password reset link is invalid or expired. Request a new one.", "invalid_reset_token", 400)
    user = User.query.filter_by(email=email).first()
    if user is None:
        return api_error("This password reset link is invalid or expired. Request a new one.", "invalid_reset_token", 400)
    user.password_hash = hash_password(password)
    db.session.commit()
    return jsonify({"message": "Your password has been reset. You can now sign in."})


@bp.get("/me")
@login_required()
def me():
    return jsonify(g.user.to_public())
