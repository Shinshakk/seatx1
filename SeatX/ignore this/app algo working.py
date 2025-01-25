from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///seatx.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Models
class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    block = db.Column(db.String(50), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    student_class = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    semester = db.Column(db.String(50), nullable=False)

class SeatingPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classroom = db.Column(db.String(100), nullable=False)
    seat = db.Column(db.String(50), nullable=False)
    roll_number = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'classrooms' in request.files and 'students' in request.files:
        classrooms_file = request.files['classrooms']
        students_file = request.files['students']

        upload_dir = os.path.join('uploads')
        os.makedirs(upload_dir, exist_ok=True)

        classrooms_path = os.path.join(upload_dir, 'classrooms.xlsx')
        students_path = os.path.join(upload_dir, 'students.xlsx')

        classrooms_file.save(classrooms_path)
        students_file.save(students_path)

        # Clear existing data from the database
        db.session.query(Student).delete()
        db.session.query(Classroom).delete()
        db.session.query(SeatingPlan).delete()
        db.session.commit()

        classrooms_df = pd.read_excel(classrooms_path)
        for _, row in classrooms_df.iterrows():
            classroom = Classroom(name=row['Classroom'], block=row['Block'], capacity=row['Capacity'])
            db.session.add(classroom)

        students_df = pd.read_excel(students_path)
        students_df = students_df.dropna(subset=['Roll Number', 'Name', 'Class', 'Department', 'Semester'])
        students_df = students_df.loc[~students_df.isnull().all(axis=1)]

        for _, row in students_df.iterrows():
            student = Student(
                roll_number=row['Roll Number'],
                name=row['Name'],
                student_class=row['Class'],
                department=row['Department'],
                semester=row['Semester']
            )
            db.session.add(student)

        db.session.commit()
        return redirect(url_for('index'))

    return "Error: Files not uploaded. Please try again."

@app.route('/generate_seating', methods=['POST'])
def generate_seating():
    classrooms = Classroom.query.all()
    students = Student.query.all()  # Do not pre-sort students here

    total_seats = sum([c.capacity for c in classrooms])
    if len(students) > total_seats:
        return f"Error: Not enough total seats available! {len(students)} students and only {total_seats} seats."

    classroom_seating = {c.name: [] for c in classrooms}
    seat_columns = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']

    seating_plan = []
    empty_seats = {c.name: [] for c in classrooms}
    student_index = 0

    for classroom in classrooms:
        available_seats = classroom.capacity
        for seat_number in range(1, available_seats + 1):
            column = seat_columns[(seat_number - 1) % len(seat_columns)]
            seat_label = f"{column}{(seat_number - 1) // len(seat_columns) + 1}"
            empty_seats[classroom.name].append(seat_label)

        current_seating = []
        for seat_number in range(1, available_seats + 1):
            if student_index >= len(students):
                break

            student = students[student_index]
            column = seat_columns[(seat_number - 1) % len(seat_columns)]
            seat_label = f"{column}{(seat_number - 1) // len(seat_columns) + 1}"

            # Assign seat
            seating_entry = {
                'classroom': classroom.name,
                'block': classroom.block,
                'seat': seat_label,
                'roll_number': student.roll_number,
                'name': student.name
            }
            current_seating.append(seating_entry)
            empty_seats[classroom.name].remove(seat_label)

            db.session.add(SeatingPlan(
                classroom=classroom.name,
                seat=seat_label,
                roll_number=student.roll_number,
                name=student.name
            ))
            student_index += 1

        classroom_seating[classroom.name] = current_seating
        seating_plan.extend(current_seating)

    # Fallback for unassigned students
    for student in students[student_index:]:
        for classroom_name, seats in empty_seats.items():
            if seats:
                seat_label = seats.pop(0)
                seating_entry = {
                    'classroom': classroom_name,
                    'block': '',
                    'seat': seat_label,
                    'roll_number': student.roll_number,
                    'name': student.name
                }
                seating_plan.append(seating_entry)
                db.session.add(SeatingPlan(
                    classroom=classroom_name,
                    seat=seat_label,
                    roll_number=student.roll_number,
                    name=student.name
                ))
                break

    # Sort the final seating plan by roll number as an integer before rendering
    sorted_seating_plan = sorted(seating_plan, key=lambda x: int(x['roll_number']))

    db.session.commit()
    return render_template('seating_plan.html', seating=sorted_seating_plan)

@app.route('/download_seating')
def download_seating():
    download_dir = os.path.join('downloads')
    os.makedirs(download_dir, exist_ok=True)

    seating_plan = SeatingPlan.query.all()
    data = sorted([{  # Sort roll numbers as integers
        'Classroom': sp.classroom,
        'Seat': sp.seat,
        'Roll Number': sp.roll_number,
        'Name': sp.name
    } for sp in seating_plan], key=lambda x: int(x['Roll Number']))

    seating_df = pd.DataFrame(data)
    output_path = os.path.join(download_dir, 'seating_plan.xlsx')
    seating_df.to_excel(output_path, index=False)

    return send_file(output_path, as_attachment=True)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
