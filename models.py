from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    roll_no = db.Column(db.String(20))


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_no = db.Column(db.String(20), unique=True, nullable=False)
    results = db.relationship('Result', backref='student', lazy=True)


class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(50), nullable=False)
    marks = db.Column(db.Integer, nullable=False)

    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('student_id', 'subject', name='unique_subject_per_student'),
    )