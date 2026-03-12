import os
import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_COOKIE_SECURE", "false")
os.environ.setdefault("JWT_COOKIE_SAMESITE", "Lax")

@pytest.fixture()
def client():
    from app import app
    from model import db

    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()

    yield app.test_client()

    with app.app_context():
        db.session.remove()
        db.drop_all()

    try:
        os.remove("test.db")
    except FileNotFoundError:
        pass
