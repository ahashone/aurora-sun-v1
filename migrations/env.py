"""
Alembic Environment Configuration for Aurora Sun V1.

This module configures the Alembic migration environment for PostgreSQL.
It sets up the SQLAlchemy engine, session, and model imports.

Usage:
    # Generate a new migration
    alembic revision --autogenerate -m "add new table"

    # Apply migrations
    alembic upgrade head

    # Rollback one migration
    alembic downgrade -1

References:
    - ARCHITECTURE.md Section 14 (Data Models)
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Import Base from consent.py (the authoritative source)
from src.models.consent import Base

# Import all models to register them with Base.metadata
from src.models.user import User
from src.models.vision import Vision
from src.models.goal import Goal
from src.models.task import Task
from src.models.daily_plan import DailyPlan
from src.models.session import Session

# This is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata for autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    """
    Get the database URL from environment or config.

    Priority:
    1. Environment variable DATABASE_URL
    2. alembic.ini sqlalchemy.url
    """
    import os
    return os.environ.get(
        "DATABASE_URL",
        config.get_main_option("sqlalchemy.url")
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a
    connection with the context.
    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


# Determine which mode to run in
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
