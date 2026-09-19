import os
import secrets
from functools import wraps

import click
from flask import (Flask, flash, redirect, render_template, request, session,
                   url_for)
from flask_wtf.csrf import CSRFError, CSRFProtect
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from models import Result, Student, User, db

csrf = CSRFProtect()

MIN_PASSWORD_LENGTH = 8


def create_app(test_config=None):
    app = Flask(__name__)

    database_url = os.environ.get("DATABASE_URL", "sqlite:///database.db")
    if database_url.startswith("postgres://"):  # older Heroku/Render style URLs
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Set SESSION_COOKIE_SECURE=1 in production (HTTPS)
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
    )
    if test_config:
        app.config.update(test_config)

    if not app.config["SECRET_KEY"]:
        # Never ship a hard-coded key. A random key works for local use, but
        # sessions reset on every restart, so set SECRET_KEY in production.
        app.logger.warning("SECRET_KEY is not set - using a temporary random key.")
        app.config["SECRET_KEY"] = secrets.token_hex(32)

    db.init_app(app)
    csrf.init_app(app)

    with app.app_context():
        db.create_all()
        _seed_admin_from_env()

    # ---------------- helpers ----------------
    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('login'))
            return view(*args, **kwargs)
        return wrapped

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('login'))
            if session.get('role') != 'admin':
                flash("Access denied", "danger")
                return redirect(url_for('index'))
            return view(*args, **kwargs)
        return wrapped

    def parse_marks(raw):
        """Return an int between 0 and 100, or None if invalid."""
        try:
            marks = int(raw)
        except (TypeError, ValueError):
            return None
        return marks if 0 <= marks <= 100 else None

    # ---------------- REGISTER (students only) ----------------
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if 'user' in session:
            return redirect(url_for('index'))

        if request.method == 'POST':
            username = (request.form.get('username') or '').strip()
            password = request.form.get('password') or ''
            roll_no = (request.form.get('roll_no') or '').strip()

            def fail(message):
                return render_template('register.html', error=message)

            if not username or not roll_no:
                return fail("Username and roll number are required")
            if len(password) < MIN_PASSWORD_LENGTH:
                return fail(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
            if User.query.filter_by(username=username).first():
                return fail("Username already exists")
            # The roll number must belong to a student the admin has already added...
            if not Student.query.filter_by(roll_no=roll_no).first():
                return fail("No student with this roll number exists. "
                            "Ask your admin to add your results first.")
            # ...and can only be linked to one account.
            if User.query.filter_by(roll_no=roll_no).first():
                return fail("This roll number is already linked to an account")

            # Role is always 'student' here - the form's role is never trusted.
            db.session.add(User(
                username=username,
                password=generate_password_hash(password),
                role='student',
                roll_no=roll_no,
            ))
            db.session.commit()

            flash("Account created successfully! Please login.", "success")
            return redirect(url_for('login'))

        return render_template('register.html')

    # ---------------- LOGIN / LOGOUT ----------------
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if 'user' in session:
            return redirect(url_for('index'))

        if request.method == 'POST':
            username = (request.form.get('username') or '').strip()
            password = request.form.get('password') or ''

            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                session.clear()  # start a fresh session on login
                session['user'] = user.username
                session['role'] = user.role
                session['roll_no'] = user.roll_no
                flash("Login successful!", "success")
                return redirect(url_for('index'))

            return render_template('login.html', error="Invalid username or password")

        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        flash("Logged out successfully", "info")
        return redirect(url_for('login'))

    # ---------------- DASHBOARD ----------------
    @app.route('/')
    @login_required
    def index():
        search = (request.args.get('search') or '').strip()
        is_admin = session['role'] == 'admin'

        # Everything shown - the table AND the statistics - is scoped by role,
        # so a student never sees other students' data or class-wide totals.
        if is_admin:
            students_q = Student.query
            results_q = Result.query
        else:
            students_q = Student.query.filter_by(roll_no=session['roll_no'])
            results_q = (Result.query.join(Student)
                         .filter(Student.roll_no == session['roll_no']))

        total_students = students_q.count()
        total_results = results_q.count()
        avg_marks = results_q.with_entities(func.avg(Result.marks)).scalar() or 0

        if search:
            like = f"%{search}%"
            students_q = students_q.filter(
                Student.name.ilike(like) | Student.roll_no.ilike(like))

        return render_template(
            'index.html',
            students=students_q.order_by(Student.roll_no).all(),
            total_students=total_students,
            total_results=total_results,
            avg_marks=round(avg_marks, 2),
            search=search,
        )

    # ---------------- ADD ----------------
    @app.route('/add', methods=['POST'])
    @admin_required
    def add_student():
        name = (request.form.get('name') or '').strip()
        roll_no = (request.form.get('roll_no') or '').strip()
        subject = (request.form.get('subject') or '').strip()
        marks = parse_marks(request.form.get('marks'))

        if not name or not roll_no or not subject:
            flash("Name, roll number and subject are required", "warning")
            return redirect(url_for('index'))
        if marks is None:
            flash("Marks must be a whole number between 0 and 100", "warning")
            return redirect(url_for('index'))

        student = Student.query.filter_by(roll_no=roll_no).first()
        if not student:
            student = Student(name=name, roll_no=roll_no)
            db.session.add(student)
            db.session.flush()

        if Result.query.filter_by(student_id=student.id, subject=subject).first():
            db.session.rollback()
            flash("Subject already exists for this student", "warning")
            return redirect(url_for('index'))

        db.session.add(Result(subject=subject, marks=marks, student_id=student.id))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Could not save this record", "danger")
            return redirect(url_for('index'))

        flash("Record added successfully!", "success")
        return redirect(url_for('index'))

    # ---------------- EDIT ----------------
    @app.route('/edit/<int:id>', methods=['GET', 'POST'])
    @admin_required
    def edit_result(id):
        result = db.get_or_404(Result, id)

        if request.method == 'POST':
            subject = (request.form.get('subject') or '').strip()
            marks = parse_marks(request.form.get('marks'))

            if not subject:
                flash("Subject is required", "warning")
                return redirect(url_for('edit_result', id=id))
            if marks is None:
                flash("Marks must be a whole number between 0 and 100", "warning")
                return redirect(url_for('edit_result', id=id))

            duplicate = Result.query.filter(
                Result.student_id == result.student_id,
                Result.subject == subject,
                Result.id != result.id,
            ).first()
            if duplicate:
                flash("This student already has a result for that subject", "warning")
                return redirect(url_for('edit_result', id=id))

            result.subject = subject
            result.marks = marks
            db.session.commit()
            flash("Record updated successfully!", "success")
            return redirect(url_for('index'))

        return render_template('edit.html', result=result)

    # ---------------- DELETE ----------------
    @app.route('/delete/<int:id>', methods=['POST'])
    @admin_required
    def delete_result(id):
        result = db.get_or_404(Result, id)
        db.session.delete(result)
        db.session.commit()
        flash("Record deleted", "info")
        return redirect(url_for('index'))

    # ---------------- ERRORS ----------------
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        flash("Your form expired or was invalid. Please try again.", "warning")
        return redirect(url_for('login' if 'user' not in session else 'index'))

    # ---------------- CLI: create the first admin ----------------
    @app.cli.command("create-admin")
    @click.argument("username")
    @click.password_option()
    def create_admin(username, password):
        """Create an admin account:  flask --app app create-admin USERNAME"""
        if User.query.filter_by(username=username).first():
            raise click.ClickException("That username already exists")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise click.ClickException(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        db.session.add(User(username=username,
                            password=generate_password_hash(password),
                            role='admin'))
        db.session.commit()
        click.echo(f"Admin '{username}' created.")

    return app


def _seed_admin_from_env():
    """Create an admin from ADMIN_USERNAME / ADMIN_PASSWORD if it doesn't exist.

    Handy on hosts without shell access (e.g. Render's free tier).
    """
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if username and password and len(password) >= MIN_PASSWORD_LENGTH:
        if not User.query.filter_by(username=username).first():
            db.session.add(User(username=username,
                                password=generate_password_hash(password),
                                role='admin'))
            db.session.commit()


app = create_app()

if __name__ == '__main__':
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
