import os

from app import create_app
from conftest import login
from models import Result, Student, User, db


# ---------- authentication ----------
def test_login_required(client):
    assert client.get("/").headers["Location"].endswith("/login")


def test_bad_login_rejected(client):
    r = login(client, "admin", "wrong")
    assert b"Invalid username or password" in r.data


def test_passwords_are_hashed(app):
    with app.app_context():
        assert User.query.filter_by(username="admin").first().password != "adminpass123"


# ---------- registration ----------
def test_cannot_register_as_admin(client, app):
    client.post("/register", data={"username": "evil", "password": "longenough1",
                                   "role": "admin", "roll_no": "101"})
    with app.app_context():
        assert User.query.filter_by(username="evil").first() is None


def test_register_requires_existing_roll_number(client):
    r = client.post("/register", data={"username": "bob", "password": "longenough1",
                                       "roll_no": "999"})
    assert b"No student with this roll number" in r.data


def test_roll_number_cannot_be_claimed_twice(client):
    r = client.post("/register", data={"username": "thief", "password": "longenough1",
                                       "roll_no": "101"})  # already linked to 'asha'
    assert b"already linked" in r.data


def test_student_can_register_for_unclaimed_roll(client, app):
    client.post("/register", data={"username": "bhav", "password": "longenough1",
                                   "roll_no": "102"})
    with app.app_context():
        u = User.query.filter_by(username="bhav").first()
        assert u.role == "student" and u.roll_no == "102"


def test_short_password_rejected(client):
    r = client.post("/register", data={"username": "bhav", "password": "short",
                                       "roll_no": "102"})
    assert b"at least 8 characters" in r.data


# ---------- data privacy ----------
def test_student_sees_only_own_records_and_stats(client):
    login(client, "asha", "studentpass1")
    page = client.get("/").data
    assert b"Asha" in page and b"Bhavesh" not in page
    assert b"80.0" in page            # her own average (90 + 70) / 2, not the class's
    assert b"66.67" not in page       # class-wide average must not be exposed


def test_student_search_cannot_reach_other_students(client):
    login(client, "asha", "studentpass1")
    # (the search text is echoed in the input box, so check the table cell)
    assert b"<td>Bhavesh</td>" not in client.get("/?search=Bhavesh").data
    assert b"<td>Bhavesh</td>" not in client.get("/?search=102").data
    assert b"No records found" in client.get("/?search=Bhavesh").data


def test_admin_sees_everyone(client):
    login(client, "admin", "adminpass123")
    page = client.get("/").data
    assert b"Asha" in page and b"Bhavesh" in page


def test_search_filters_for_admin(client):
    login(client, "admin", "adminpass123")
    page = client.get("/?search=bhav").data
    assert b"Bhavesh" in page and b"Asha" not in page


# ---------- authorisation ----------
def test_student_cannot_add_edit_delete(client, app):
    login(client, "asha", "studentpass1")
    client.post("/add", data={"name": "X", "roll_no": "300", "subject": "Art", "marks": 50})
    with app.app_context():
        rid = Result.query.first().id
    client.post(f"/edit/{rid}", data={"subject": "Hacked", "marks": 1})
    client.post(f"/delete/{rid}")
    with app.app_context():
        assert Student.query.filter_by(roll_no="300").first() is None
        assert db.session.get(Result, rid) is not None
        assert db.session.get(Result, rid).subject != "Hacked"


# ---------- admin CRUD ----------
def test_admin_add_result(client, app):
    login(client, "admin", "adminpass123")
    client.post("/add", data={"name": "Chirag", "roll_no": "103", "subject": "Art", "marks": 88})
    with app.app_context():
        s = Student.query.filter_by(roll_no="103").first()
        assert s and s.results[0].marks == 88


def test_marks_validated(client, app):
    login(client, "admin", "adminpass123")
    for bad in ("101", "-1", "abc", ""):
        client.post("/add", data={"name": "Z", "roll_no": "104", "subject": "Art", "marks": bad})
    with app.app_context():
        assert Student.query.filter_by(roll_no="104").first() is None


def test_duplicate_subject_rejected(client, app):
    login(client, "admin", "adminpass123")
    client.post("/add", data={"name": "Asha", "roll_no": "101", "subject": "Maths", "marks": 10})
    with app.app_context():
        assert Result.query.join(Student).filter(
            Student.roll_no == "101", Result.subject == "Maths").count() == 1


def test_edit_page_renders_and_saves(client, app):
    login(client, "admin", "adminpass123")
    with app.app_context():
        rid = Result.query.filter_by(subject="Physics").first().id
    assert client.get(f"/edit/{rid}").status_code == 200   # edit.html exists
    client.post(f"/edit/{rid}", data={"subject": "Physics", "marks": 75})
    with app.app_context():
        assert db.session.get(Result, rid).marks == 75


def test_edit_cannot_create_duplicate_subject(client, app):
    login(client, "admin", "adminpass123")
    with app.app_context():
        rid = Result.query.filter_by(subject="Physics").first().id
    client.post(f"/edit/{rid}", data={"subject": "Maths", "marks": 75})
    with app.app_context():
        assert db.session.get(Result, rid).subject == "Physics"


def test_admin_delete(client, app):
    login(client, "admin", "adminpass123")
    with app.app_context():
        rid = Result.query.filter_by(subject="Physics").first().id
    client.post(f"/delete/{rid}")
    with app.app_context():
        assert db.session.get(Result, rid) is None


# ---------- security ----------
def test_csrf_blocks_forged_post(tmp_path):
    os.environ["DATABASE_URL"] = "sqlite:///" + str(tmp_path / "csrf.db")
    app = create_app({"TESTING": True, "SECRET_KEY": "k"})  # CSRF left ON
    c = app.test_client()
    r = c.post("/login", data={"username": "a", "password": "b"})
    assert r.status_code == 302 and "/login" in r.headers["Location"]  # rejected, not processed


def test_admin_seeded_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "seed.db"))
    monkeypatch.setenv("ADMIN_USERNAME", "boss")
    monkeypatch.setenv("ADMIN_PASSWORD", "supersecret1")
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SECRET_KEY": "k"})
    assert login(app.test_client(), "boss", "supersecret1").status_code == 200
    with app.app_context():
        assert User.query.filter_by(username="boss").first().role == "admin"
