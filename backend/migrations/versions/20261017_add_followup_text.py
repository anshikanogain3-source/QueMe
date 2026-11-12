"""Store generated follow-up text on its interview question instance.

Revision ID: 20261017_followup_text
Revises: 8e83646f0010
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa


revision = "20261017_followup_text"
down_revision = "8e83646f0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("interview_questions", sa.Column("followup_text", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("interview_questions", "followup_text")
