from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Importa los modelos para que queden registrados en SQLModel.metadata
from app import models  # noqa: F401


def _normalize(url: str) -> str:
    """Railway/Heroku entregan 'postgresql://...'; SQLAlchemy async necesita '+asyncpg'."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(_normalize(settings.database_url), echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

