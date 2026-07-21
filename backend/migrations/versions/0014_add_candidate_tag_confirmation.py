"""add candidate tag confirmation

Revision ID: 0014_add_candidate_tag_confirmation
Revises: 0013_add_system_settings
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_add_candidate_tag_confirmation"
down_revision = "0013_add_system_settings"
branch_labels = None
depends_on = None


def upgrade():
    add_column_if_missing("candidate_tag", sa.Column("evidence_override", sa.Boolean(), nullable=False, server_default=sa.false()))
    add_column_if_missing("candidate_tag", sa.Column("evidence_note", sa.String(length=255), nullable=False, server_default=""))
    add_column_if_missing("candidate_tag", sa.Column("confirmed_by", sa.Integer(), nullable=True))
    add_column_if_missing("candidate_tag", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    create_foreign_key_if_missing("candidate_tag", "fk_candidate_tag_confirmed_by_user", ["confirmed_by"], "user", ["id"])


def downgrade():
    drop_foreign_key_if_exists("candidate_tag", "fk_candidate_tag_confirmed_by_user")
    drop_column_if_exists("candidate_tag", "confirmed_at")
    drop_column_if_exists("candidate_tag", "confirmed_by")
    drop_column_if_exists("candidate_tag", "evidence_note")
    drop_column_if_exists("candidate_tag", "evidence_override")


def add_column_if_missing(table_name, column):
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns(table_name)}
    if column.name not in columns:
        op.add_column(table_name, column)


def drop_column_if_exists(table_name, column_name):
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name in columns:
        op.drop_column(table_name, column_name)


def create_foreign_key_if_missing(table_name, constraint_name, local_cols, remote_table, remote_cols):
    if op.get_bind().dialect.name == "sqlite":
        return
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_foreign_keys(table_name)}
    if constraint_name not in existing:
        op.create_foreign_key(constraint_name, table_name, remote_table, local_cols, remote_cols)


def drop_foreign_key_if_exists(table_name, constraint_name):
    if op.get_bind().dialect.name == "sqlite":
        return
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_foreign_keys(table_name)}
    if constraint_name in existing:
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")
