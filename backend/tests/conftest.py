"""Pytest configuration / fixtures.

Sets required env vars BEFORE importing the app so that pydantic-settings
validators (e.g. SECRET_KEY length check) are satisfied. Wires an in-memory
SQLite DB shared across the request and the test via StaticPool, and overrides
the FastAPI `get_db` dependency.
"""

import os
import sys
from pathlib import Path

# Required env vars must be set BEFORE app import.
os.environ.setdefault("SECRET_KEY", "x" * 64)
os.environ.setdefault("GEMINI_API_KEY", "")
# Force tests to use the in-memory DB independent of any .env
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Make the `backend/` directory importable so `from app...` works regardless
# of where pytest is invoked from.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite needs PRAGMA foreign_keys=ON for cascade-delete to fire.
    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    from app.core.database import Base
    from app.models import models  # noqa: F401  ensure models register

    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def TestingSessionLocal(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session(TestingSessionLocal):
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client(TestingSessionLocal):
    from app.main import app
    from app.core.database import get_db

    def _override_get_db():
        s = TestingSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
