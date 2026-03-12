import importlib.util
import os
import sys
import types
import unittest

if importlib.util.find_spec("flask_migrate") is None:
    flask_migrate = types.ModuleType("flask_migrate")

    class DummyMigrate:
        def __init__(self, *args, **kwargs):
            pass

    flask_migrate.Migrate = DummyMigrate
    sys.modules["flask_migrate"] = flask_migrate

os.environ.setdefault("DATABASE_URL", "sqlite:///test_register.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from app import app
from model import User, db


class TestRegisterPasswordValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.drop_all()
        try:
            os.remove("test_register.db")
        except FileNotFoundError:
            pass

    def setUp(self):
        with self.app.app_context():
            db.session.query(User).delete()
            db.session.commit()

    def test_rejects_weak_passwords(self):
        weak_cases = [
            ("short1", "Password must be at least 8 characters."),
            ("12345678", "Password must contain letters."),
            ("Password", "Password must contain numbers."),
        ]

        for password, expected_error in weak_cases:
            with self.subTest(password=password):
                response = self.client.post(
                    "/api/register",
                    json={
                        "email": "weak@example.com",
                        "password": password,
                        "name": "Weak User",
                    },
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json(), {"error": expected_error})

    def test_accepts_valid_password(self):
        response = self.client.post(
            "/api/register",
            json={
                "email": "valid@example.com",
                "password": "Strongpass1",
                "name": "Valid User",
                "role": "job-seeker",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["message"], "registered")
        self.assertEqual(payload["user"]["email"], "valid@example.com")


if __name__ == "__main__":
    unittest.main()