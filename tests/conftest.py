import pytest
from fastapi.testclient import TestClient

from app.backend.main import create_app


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def client(db_url):
    with TestClient(create_app(db_url, webhook_secret="")) as test_client:
        yield test_client


@pytest.fixture
def payload():
    return {"tariff_id": 2, "email": "student@example.com", "method": "card"}
