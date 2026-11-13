import logging
import time
import uuid
from pathlib import Path

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

from config import Config, validate_config
from .extensions import db, migrate
from .logging_config import configure_logging, log_api_request


def create_app(config_object=None):
    app = Flask(__name__)
    if isinstance(config_object, dict):
        app.config.from_mapping(config_object)
    else:
        app.config.from_object(config_object or Config)
    validate_config(app)
    configure_logging(app)
    if app.config.get("MAX_AUDIO_BYTES") is None:
        app.config["MAX_AUDIO_BYTES"] = 25 * 1024 * 1024
    if app.config.get("MAX_CONTENT_LENGTH") is None:
        app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

    db.init_app(app)
    migration_dir = Path(__file__).resolve().parent.parent / "migrations"
    migrate.init_app(app, db, directory=str(migration_dir))
    CORS(app, resources={r"/api/*": {"origins": app.config["FRONTEND_ORIGIN"]}})

    # Import models before migration commands inspect SQLAlchemy metadata.
    from . import models  # noqa: F401
    from .blueprints.admin import bp as admin_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.reports import bp as reports_bp
    from .blueprints.session import bp as session_bp
    from .blueprints.teacher import bp as teacher_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(teacher_bp, url_prefix="/api")
    app.register_blueprint(session_bp, url_prefix="/api")
    app.register_blueprint(reports_bp, url_prefix="/api")

    @app.before_request
    def begin_api_request():
        if request_is_api():
            g.request_id = uuid.uuid4().hex
            g.request_started_at = time.perf_counter()

    @app.after_request
    def log_api_response(response):
        if request_is_api():
            request_id = getattr(g, "request_id", None) or uuid.uuid4().hex
            response.headers["X-Request-ID"] = request_id
            log_api_request(
                logging.getLogger("queme.access"),
                getattr(g, "request_started_at", None) or time.perf_counter(),
                request_id,
                response,
            )
        return response

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        if request_is_api():
            code = error.name.lower().replace(" ", "_")
            return jsonify({"error": error.description, "code": code}), error.code
        return error

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(error):
        db.session.rollback()
        app.logger.warning("Database integrity conflict handled error_type=%s", type(error).__name__)
        return jsonify({"error": "The request conflicts with existing data.", "code": "data_conflict"}), 409

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        if isinstance(error, HTTPException):
            return handle_http_error(error)
        db.session.rollback()
        app.logger.exception("Unhandled application error")
        return jsonify({"error": "An unexpected server error occurred.", "code": "internal_error"}), 500

    @app.get("/api/health")
    def health():
        from .services.answer_jobs import worker_health

        worker = worker_health()
        try:
            db.session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Database health check failed")
            return jsonify({"status": "unavailable", "database": "unavailable", "worker": worker}), 503
        return jsonify({"status": "ok", "database": "ok", "worker": worker})

    register_cli_commands(app)
    return app


def request_is_api():
    return request.path.startswith("/api/")


def register_cli_commands(app):
    import click

    from .authz import hash_password
    from .academics import COURSES
    from .models import Department, Rubric, SystemSetting, User

    @app.cli.command("seed")
    def seed_database():
        """Create the initial admin, default rubrics, and score weights."""
        email = app.config.get("ADMIN_EMAIL", "").strip().lower()
        password = app.config.get("ADMIN_PASSWORD", "")
        full_name = app.config.get("ADMIN_FULL_NAME", "QueMe Administrator").strip()
        if not email or "@" not in email:
            raise click.ClickException("Set a valid ADMIN_EMAIL in .env before running flask seed.")
        if len(password) < 12:
            raise click.ClickException("Set ADMIN_PASSWORD to at least 12 characters before running flask seed.")
        if not full_name:
            raise click.ClickException("ADMIN_FULL_NAME cannot be empty.")

        criteria = {
            "Technical Answer": ["Relevance", "Correctness", "Explanation", "Completeness"],
            "HR Answer": ["Relevance", "Clarity", "Self-awareness", "Structure"],
            "Behavioral Answer": ["Specific example", "Action", "Result", "Clarity"],
            "Communication Answer": ["Clarity", "Organization", "Fluency", "Relevance"],
        }

        try:
            user = User.query.filter_by(email=email).first()
            if user and user.role != "admin":
                raise click.ClickException(
                    f"{email} already belongs to a non-admin account; choose a different ADMIN_EMAIL."
                )
            if not user:
                user = User(
                    full_name=full_name,
                    email=email,
                    password_hash=hash_password(password),
                    role="admin",
                    account_status="ACTIVE",
                )
                db.session.add(user)
            else:
                user.account_status = "ACTIVE"
            db.session.flush()

            for course_name in COURSES:
                if not any(row.department_name.lower() == course_name.lower() for row in Department.query.all()):
                    db.session.add(Department(department_name=course_name))

            for name, items in criteria.items():
                rubric = Rubric.query.filter_by(rubric_name=name).first()
                if rubric is None:
                    db.session.add(
                        Rubric(
                            rubric_name=name,
                            rubric_type=name.split()[0].lower(),
                            criteria_json={"criteria": items},
                            maximum_score=10,
                            created_by=user.user_id if user.user_id else None,
                        )
                    )

            defaults = {
                "content_weight": str(app.config.get("CONTENT_WEIGHT", 0.70)),
                "delivery_weight": str(app.config.get("DELIVERY_WEIGHT", 0.30)),
            }
            for key, value in defaults.items():
                if db.session.get(SystemSetting, key) is None:
                    db.session.add(SystemSetting(key=key, value=value))

            db.session.commit()
        except click.ClickException:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            app.logger.exception("Initial database seeding failed")
            raise click.ClickException(f"Initial data could not be seeded: {exc}") from exc

        click.echo("Initial data is ready (admin, courses, default rubrics, and score weights).")

    @app.cli.command("process-answer-jobs")
    @click.option("--once", is_flag=True, help="Process one available job and exit.")
    @click.option("--poll-seconds", type=click.FloatRange(min=0.1), default=1.0, show_default=True)
    def process_answer_jobs(once, poll_seconds):
        """Run the single local worker for queued interview answers."""
        from .services.answer_jobs import run_worker

        try:
            run_worker(once=once, poll_seconds=poll_seconds)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc
