"""Async + sync SQLAlchemy session factories.

The async path serves the FastAPI request handlers. The sync path serves
Celery workers (Celery's task model is sync) and Alembic migrations.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from omnix.cloud.config import get_settings


@lru_cache(maxsize=1)
def get_async_engine():
    settings = get_settings()
    return create_async_engine(settings.database_url, future=True, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sync_engine():
    settings = get_settings()
    return create_engine(settings.sync_database_url, future=True, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_async_session_maker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_async_engine(), expire_on_commit=False, class_=AsyncSession)


@lru_cache(maxsize=1)
def get_sync_session_maker() -> sessionmaker[Session]:
    return sessionmaker(get_sync_engine(), expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def async_session_scope() -> AsyncIterator[AsyncSession]:
    sm = get_async_session_maker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@contextmanager
def sync_session_scope() -> Iterator[Session]:
    sm = get_sync_session_maker()
    session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
