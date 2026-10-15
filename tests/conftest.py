"""Configuración de tests.

IMPORTANTE: la config (`app.config.settings`) y el motor de base de datos
(`app.db.engine`) se construyen al importar. Por eso definimos variables de
entorno FALSAS ANTES de importar cualquier módulo de `app`, garantizando:
  - SQLite temporal (nada de Postgres remoto),
  - cero red (token y API key falsos; nunca se llama a Telegram ni Gemini),
  - aislamiento: las tablas se recrean antes de cada test.
"""

import os
import tempfile

# --- Entorno fake ANTES de importar app ---
os.environ["TELEGRAM_BOT_TOKEN"] = "1234567890:" + "A" * 35  # formato válido, sin uso real
os.environ["GEMINI_API_KEY"] = "test-key-sin-red"
_DB_PATH = os.path.join(tempfile.gettempdir(), "bitacora_tests.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"

import pytest_asyncio  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.db import engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db():
    """Recrea las tablas antes de cada test (aislamiento total, sin red)."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
