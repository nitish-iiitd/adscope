import os
import tempfile

import pytest

# Configure the environment before app modules read settings at import time.
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()

os.environ.update(
    {
        "APP_USERNAME": "admin",
        "APP_PASSWORD": "test-password",
        "SESSION_SECRET": "test-secret",
        "DEMO_MODE": "true",
        "DATABASE_URL": f"sqlite:///{_tmp_db.name}",
        "COOKIE_SECURE": "false",
        # Blank the provider keys so a developer's real .env can never leak into the
        # tests and fire billable API calls. Env vars win over .env in pydantic-settings.
        "GEMINI_API_KEY": "",
        "GROQ_API_KEY": "",
        "OPENROUTER_API_KEY": "",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def anyio_backend():
    """anyio's pytest plugin ships with httpx; run async tests on asyncio only."""
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "test-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client
