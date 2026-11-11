"""Shared fixtures: a transactional session on marginos_test and a TestClient bound to it."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("APP_ENV", "development")

from marginos.core.config import get_settings  # noqa: E402
from marginos.core.db import Base, get_db, get_session_scope  # noqa: E402
from marginos.core.models_registry import import_all_models  # noqa: E402
from marginos.main import create_app  # noqa: E402

import_all_models()


def _test_database_url(url: str) -> str:
    base, _, dbname = url.rpartition("/")
    return f"{base}/{dbname}_test"


TEST_DATABASE_URL = _test_database_url(get_settings().database_url)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Generator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient]:
    app = create_app()

    def _override() -> Generator[Session]:
        yield db

    @contextmanager
    def _scope() -> Generator[Session]:
        yield db
        db.flush()

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_session_scope] = lambda: _scope
    with TestClient(app) as c:
        yield c
