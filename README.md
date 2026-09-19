# Student Result Management System

A Flask web app where **admins** manage student results and **students** view only their own.

## Features
- Registration and login with hashed passwords (Werkzeug) and session-based auth
- Role-based access control: admin-only add / edit / delete; students see only their own records **and** their own statistics
- Dashboard with total students, total results and average marks (scoped by role)
- Search by name or roll number (server-side)
- Input validation (marks 0-100, required fields) and a unique constraint per student and subject
- CSRF protection on every form (Flask-WTF)
- Pytest suite covering authentication, authorisation, privacy and CRUD

## Tech stack
Python · Flask · SQLAlchemy (SQLite) · Bootstrap 5 · pytest

## Run locally
```bash
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

# create the first admin (asks for a password)
flask --app app create-admin yourusername

flask --app app run --debug
```
Open http://127.0.0.1:5000

## How accounts work
1. An admin logs in and adds a student's results (this creates the student record).
2. The student registers with their **roll number**. The roll number must already exist and can only be linked to one account.
3. Admin accounts cannot be created through the registration form.

## Configuration (environment variables)
| Variable | Purpose |
|---|---|
| `SECRET_KEY` | **Required in production.** Long random string used to sign sessions |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Optional: creates this admin on startup if missing (useful on hosts without a shell) |
| `DATABASE_URL` | Optional, defaults to `sqlite:///database.db` |
| `SESSION_COOKIE_SECURE` | Set to `1` when served over HTTPS |

See `.env.example`. Never commit `.env` or any `*.db` file.

## Deploy (Render)
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Add `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` and `SESSION_COOKIE_SECURE=1` under Environment.

## Run the tests
```bash
pytest
```

## Known limitations
- The first person to register a roll number claims it. A production system should use a per-student invite code or admin-created accounts.
- SQLite on free hosting can be reset on redeploy; use a hosted database for real data.
