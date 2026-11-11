"""Shared fixtures: a transactional session on marginos_test and a TestClient bound to it."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("APP_ENV", "development")

from marginos.core.config import get_settings  # noqa: E402
from marginos.core.db import Base, get_db  # noqa: E402
from marginos.main import create_app  # noqa: E402

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
def db(engine) -> Generator[Session, None, None]:
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
def client(db: Session) -> Generator[TestClient, None, None]:
    app = create_app()

    def _override() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
