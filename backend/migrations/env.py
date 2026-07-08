from logging.config import fileConfig

from alembic import context
from flask import current_app
from sqlalchemy import text

config = context.config
fileConfig(config.config_file_name)

db = current_app.extensions["migrate"].db
target_metadata = db.metadata


def get_url():
    return str(db.engine.url).replace("%", "%%")


def run_migrations_offline():
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with db.engine.connect() as connection:
        ensure_version_table_capacity(connection)
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


def ensure_version_table_capacity(connection):
    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(128) NOT NULL PRIMARY KEY
            )
            """
        )
    )
    connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"))
    connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
