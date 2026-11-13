"""Add durable answer processing jobs and enforce one report per interview.

Revision ID: 20261113_answer_processing_jobs
Revises: 20261024_reporting_analytics
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa


revision = "20261113_answer_processing_jobs"
down_revision = "20261024_reporting_analytics"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    duplicate = connection.execute(sa.text(
        "SELECT interview_id FROM reports "
        "WHERE interview_id IS NOT NULL GROUP BY interview_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate:
        raise RuntimeError(
            "Cannot enforce one report per interview: duplicate reports exist. "
            "Resolve them explicitly before applying this migration."
        )

    op.create_table(
        "answer_processing_jobs",
        sa.Column("job_id", sa.Integer(), primary_key=True),
        sa.Column(
            "interview_question_id",
            sa.Integer(),
            sa.ForeignKey("interview_questions.interview_question_id"),
            nullable=False,
        ),
        sa.Column("submission_id", sa.String(length=64), nullable=False),
        sa.Column("audio_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=60), nullable=True),
        sa.Column("last_error_message", sa.String(length=300), nullable=True),
        sa.UniqueConstraint("interview_question_id", name="uq_answer_job_question"),
        sa.UniqueConstraint("submission_id", name="uq_answer_job_submission"),
    )
    op.create_index(
        "ix_answer_job_status_available",
        "answer_processing_jobs",
        ["status", "available_at"],
    )
    op.create_index("uq_reports_interview_id", "reports", ["interview_id"], unique=True)


def downgrade():
    op.drop_index("uq_reports_interview_id", table_name="reports")
    op.drop_index("ix_answer_job_status_available", table_name="answer_processing_jobs")
    op.drop_table("answer_processing_jobs")
