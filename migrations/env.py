"""Entorno Alembic — async, coherente con los URLs reales del proyecto.

Reutiliza `app.db._normalize` (sqlite+aiosqlite / postgresql+asyncpg). La URL
sale de DATABASE_URL de la app, salvo que un test la fije en el config.
"""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from app import models  # noqa: F401  (registra las tablas en metadata)
from app.config import settings
from app.db import _normalize

config = context.config
target_metadata = SQLModel.metadata


def _url() -> str:
    override = config.get_main_option("sqlalchemy.url")
    return _normalize(override) if override else _normalize(settings.database_url)


def _run_sync_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync_migrations)
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=_url(), target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
