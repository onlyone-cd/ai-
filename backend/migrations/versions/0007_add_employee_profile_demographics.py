"""add employee profile demographics

Revision ID: 0007_add_employee_profile_demographics
Revises: 0006_add_internal_talent
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_add_employee_profile_demographics"
down_revision = "0006_add_internal_talent"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("employee_profile") as batch_op:
        batch_op.add_column(sa.Column("birth_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("education", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("graduation_school", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("graduation_date", sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table("employee_profile") as batch_op:
        batch_op.drop_column("graduation_date")
        batch_op.drop_column("graduation_school")
        batch_op.drop_column("education")
        batch_op.drop_column("birth_date")
