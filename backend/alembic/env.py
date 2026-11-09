"""Alembic environment.

Ownership (see docs/database/MIGRATION_GUIDE.md): Alembic owns every object in the `public` and `app`
schemas. Step 4 wraps database/migrations/0001..0009 as revisions. Supabase-managed schemas (auth, storage,
extensions) are never touched. No revision exists yet, so `alembic upgrade head` is a no-op.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers models on Base.metadata)
from alembic import context
from app.core.config import get_settings
from app.database.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    url = get_settings().sqlalchemy_url
    if url is None:
        raise SystemExit(
            "DATABASE_URL is not set. Configure backend/.env (see .env.example) and retry."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        _database_url(), poolclass=pool.NullPool, connect_args={"prepare_threshold": None}
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
