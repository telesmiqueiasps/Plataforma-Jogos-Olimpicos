from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# ---------------------------------------------------------------------------
# Sync engine  (usado por rotas FastAPI existentes via Depends(get_db))
# ---------------------------------------------------------------------------

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Async engine  (usado por standings_service e outros serviços heavy)
# Driver: asyncpg  →  postgresql+asyncpg://
# ---------------------------------------------------------------------------

_async_url = (
    settings.DATABASE_URL
    .replace("postgresql://", "postgresql+asyncpg://", 1)
    .replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
)

async_engine = create_async_engine(_async_url, pool_pre_ping=True, pool_size=10, max_overflow=20)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
