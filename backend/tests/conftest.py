import pytest

from app import create_app, db
from app.config import TestConfig


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_headers(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = response.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def recruiter_headers(client):
    response = client.post("/api/auth/login", json={"username": "recruiter", "password": "admin123"})
    token = response.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
