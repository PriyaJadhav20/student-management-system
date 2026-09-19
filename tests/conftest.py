import os
import tempfile

import pytest

# Point the module-level app at a throwaway DB before it is imported.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmp, "import.db")
os.environ.pop("ADMIN_USERNAME", None)
os.environ.pop("ADMIN_PASSWORD", None)

from app import create_app  # noqa: E402
from models import db, Student, Result, User  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


@pytest.fixture
def app(tmp_path):
    os.environ["DATABASE_URL"] = "sqlite:///" + str(tmp_path / "test.db")
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SECRET_KEY": "test-key"})
    with app.app_context():
        db.session.add(User(username="admin", role="admin",
                            password=generate_password_hash("adminpass123")))
        a = Student(name="Asha", roll_no="101")
        b = Student(name="Bhavesh", roll_no="102")
        db.session.add_all([a, b])
        db.session.flush()
        db.session.add_all([
            Result(subject="Maths", marks=90, student_id=a.id),
            Result(subject="Physics", marks=70, student_id=a.id),
            Result(subject="Maths", marks=40, student_id=b.id),
        ])
        db.session.add(User(username="asha", role="student", roll_no="101",
                            password=generate_password_hash("studentpass1")))
        db.session.commit()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username, password):
    return client.post("/login", data={"username": username, "password": password},
                       follow_redirects=True)
