from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, Student, Result, User
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "secret123"

# --- CONFIG ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()


# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    # Prevent accessing register if already logged in
    if 'user' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        roll_no = request.form.get('roll_no')

        if User.query.filter_by(username=username).first():
            return render_template('register.html', error="Username already exists")

        if role == 'student' and not roll_no:
            return render_template('register.html', error="Roll number required")

        # Optional: block admin registration
        if role == 'admin':
            return render_template('register.html', error="Admin registration not allowed")

        new_user = User(
            username=username,
            password=generate_password_hash(password),
            role=role,
            roll_no=roll_no if role == 'student' else None
        )

        db.session.add(new_user)
        db.session.commit()

        flash("Account created successfully! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Prevent login if already logged in
    if 'user' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user'] = user.username
            session['role'] = user.role
            session['roll_no'] = user.roll_no

            flash("Login successful!", "success")
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid username or password")

    return render_template('login.html')


# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for('login'))


# ---------------- HOME ----------------
@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))

    search = request.args.get('search')

    if session['role'] == 'admin':
        query = Student.query
    else:
        query = Student.query.filter_by(roll_no=session['roll_no'])

    if search:
        query = query.filter(
            (Student.name.ilike(f"%{search}%")) |
            (Student.roll_no.ilike(f"%{search}%"))
        )

    students = query.all()

    total_students = Student.query.count()
    total_results = Result.query.count()
    avg_marks = db.session.query(func.avg(Result.marks)).scalar() or 0

    return render_template(
        'index.html',
        students=students,
        total_students=total_students,
        total_results=total_results,
        avg_marks=round(avg_marks, 2)
    )


# ---------------- ADD ----------------
@app.route('/add', methods=['POST'])
def add_student():
    if session.get('role') != 'admin':
        flash("Access Denied", "danger")
        return redirect(url_for('index'))

    try:
        name = request.form.get('name')
        roll_no = request.form.get('roll_no')
        subject = request.form.get('subject')
        marks = int(request.form.get('marks'))

        if marks < 0 or marks > 100:
            flash("Marks must be between 0 and 100", "warning")
            return redirect(url_for('index'))

        student = Student.query.filter_by(roll_no=roll_no).first()

        if not student:
            student = Student(name=name, roll_no=roll_no)
            db.session.add(student)
            db.session.flush()

        existing = Result.query.filter_by(
            student_id=student.id, subject=subject
        ).first()

        if existing:
            flash("Subject already exists", "warning")
            return redirect(url_for('index'))

        new_result = Result(
            subject=subject,
            marks=marks,
            student_id=student.id
        )

        db.session.add(new_result)
        db.session.commit()

        flash("Record added successfully!", "success")
        return redirect(url_for('index'))

    except Exception as e:
        return f"Error: {str(e)}"


# ---------------- DELETE ----------------
@app.route('/delete/<int:id>', methods=['POST'])
def delete_result(id):
    if session.get('role') != 'admin':
        flash("Access Denied", "danger")
        return redirect(url_for('index'))

    result = Result.query.get_or_404(id)
    db.session.delete(result)
    db.session.commit()

    flash("Record deleted", "info")
    return redirect(url_for('index'))


# ---------------- EDIT ----------------
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_result(id):
    if session.get('role') != 'admin':
        flash("Access Denied", "danger")
        return redirect(url_for('index'))

    result = Result.query.get_or_404(id)

    if request.method == 'POST':
        try:
            result.subject = request.form.get('subject')
            marks = int(request.form.get('marks'))

            if marks < 0 or marks > 100:
                flash("Invalid marks", "warning")
                return redirect(url_for('index'))

            result.marks = marks
            db.session.commit()

            flash("Record updated successfully!", "success")
            return redirect(url_for('index'))

        except:
            return "Error updating record"

    return render_template('edit.html', result=result)



@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    return render_template('admin.html')



# ---------------- RUN ----------------
if __name__ == '__main__':
    app.run(debug=True)