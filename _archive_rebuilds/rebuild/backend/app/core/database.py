import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import settings

_pool_kwargs = (
    {"poolclass": NullPool}
    if os.environ.get("TESTING")
    else {
        "pool_size": settings.pool_size,
        "max_overflow": settings.max_overflow,
        "pool_timeout": settings.pool_timeout,
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={
        "server_settings": {
            "statement_timeout": str(settings.statement_timeout_ms),
        }
    },
    **_pool_kwargs,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    session = async_session()
    try:
        yield session
    finally:
        await session.close()
