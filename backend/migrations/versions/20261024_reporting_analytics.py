"""Add question topic tags and auditable teacher review records.

Revision ID: 20261024_reporting_analytics
Revises: 20261017_followup_text
Create Date: 2026-10-24
"""
from alembic import op
import sqlalchemy as sa


revision = "20261024_reporting_analytics"
down_revision = "20261017_followup_text"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("question_bank", sa.Column("topics_json", sa.JSON(), nullable=True))
    op.create_table(
        "question_reviews",
        sa.Column("review_id", sa.Integer(), primary_key=True),
        sa.Column(
            "interview_question_id",
            sa.Integer(),
            sa.ForeignKey("interview_questions.interview_question_id"),
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("rubric_version", sa.String(length=40), nullable=True),
        sa.Column("ai_score", sa.Numeric(4, 2), nullable=True),
        sa.Column("teacher_score", sa.Numeric(4, 2), nullable=True),
        sa.Column("ai_criteria_json", sa.JSON(), nullable=True),
        sa.Column("teacher_criteria_json", sa.JSON(), nullable=True),
        sa.Column("teacher_remark", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("question_reviews")
    op.drop_column("question_bank", "topics_json")
