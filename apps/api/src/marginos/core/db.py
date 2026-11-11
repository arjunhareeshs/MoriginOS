"""SQLAlchemy engine, session factory and declarative base."""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from marginos.core.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def SessionLocal() -> Session:  # noqa: N802 - conventional name
    return _session_factory()()


def get_db() -> Generator[Session]:
    """FastAPI dependency: one session per request, closed afterwards."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session]:
    """Commit on success, roll back on error. For background work outside requests."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


SessionScope = Callable[[], AbstractContextManager[Session]]


def get_session_scope() -> SessionScope:
    """Dependency for background work: returns the factory, so tests can substitute it."""
    return session_scope
