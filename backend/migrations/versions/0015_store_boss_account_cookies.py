"""store boss account cookies

Revision ID: 0015_store_boss_account_cookies
Revises: 0014_add_candidate_tag_confirmation
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_store_boss_account_cookies"
down_revision = "0014_add_candidate_tag_confirmation"
branch_labels = None
depends_on = None


def upgrade():
    add_column_if_missing("boss_account", sa.Column("cookie_encrypted", sa.Text(), nullable=True))
    add_column_if_missing("boss_account", sa.Column("cookie_count", sa.Integer(), nullable=False, server_default="0"))
    add_column_if_missing("boss_account", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    add_column_if_missing("boss_account", sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
    add_column_if_missing("boss_account", sa.Column("last_verified_ok", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE boss_account SET cookie_count = COALESCE(cookie_count, 0)")
    op.execute("UPDATE boss_account SET is_active = TRUE WHERE is_active IS NULL")
    op.execute("UPDATE boss_account SET last_verified_ok = COALESCE(verified, FALSE) WHERE last_verified_ok IS NULL")
    create_index_if_missing("ix_boss_account_owner_active", "boss_account", ["owner_hr_id", "is_active"])


def downgrade():
    drop_index_if_exists("ix_boss_account_owner_active", "boss_account")
    drop_column_if_exists("boss_account", "last_verified_ok")
    drop_column_if_exists("boss_account", "last_verified_at")
    drop_column_if_exists("boss_account", "is_active")
    drop_column_if_exists("boss_account", "cookie_count")
    drop_column_if_exists("boss_account", "cookie_encrypted")


def table_columns(table_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def add_column_if_missing(table_name, column):
    if column.name not in table_columns(table_name):
        op.add_column(table_name, column)


def drop_column_if_exists(table_name, column_name):
    if column_name in table_columns(table_name):
        op.drop_column(table_name, column_name)


def create_index_if_missing(index_name, table_name, columns):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def drop_index_if_exists(index_name, table_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)
