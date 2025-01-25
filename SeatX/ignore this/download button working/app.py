from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import os
import smtplib
from email.mime.text import MIMEText

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
    email = db.Column(db.String(100), nullable=False)
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
        students_df = students_df.dropna(subset=['Roll Number', 'Name', 'Email', 'Class', 'Department', 'Semester'])
        for _, row in students_df.iterrows():
            student = Student(
                roll_number=row['Roll Number'],
                name=row['Name'],
                email=row['Email'],
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
    students = Student.query.all()

    total_seats = sum([c.capacity for c in classrooms])
    if len(students) > total_seats:
        return f"Error: Not enough total seats available! {len(students)} students and only {total_seats} seats."

    seating_plan = []
    seat_columns = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']
    student_index = 0

    for classroom in classrooms:
        available_seats = classroom.capacity
        for seat_number in range(1, available_seats + 1):
            if student_index >= len(students):
                break

            student = students[student_index]
            column = seat_columns[(seat_number - 1) % len(seat_columns)]
            seat_label = f"{column}{(seat_number - 1) // len(seat_columns) + 1}"

            seating_entry = {
                'classroom': classroom.name,
                'block': classroom.block,
                'seat': seat_label,
                'roll_number': student.roll_number,
                'name': student.name
            }
            seating_plan.append(seating_entry)

            db.session.add(SeatingPlan(
                classroom=classroom.name,
                seat=seat_label,
                roll_number=student.roll_number,
                name=student.name
            ))
            student_index += 1

    db.session.commit()
    return render_template('seating_plan.html', seating=seating_plan)

@app.route('/send_notifications', methods=['POST'])
def send_notifications():
    students = Student.query.all()
    seating_plan = {sp.roll_number: sp for sp in SeatingPlan.query.all()}

    sender_email = "seatx.app@gmail.com"
    sender_password = "vugo bnrz eueb fakr"

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(sender_email, sender_password)

        for student in students:
            if student.roll_number in seating_plan:
                seating = seating_plan[student.roll_number]
                message = f"""
                Dear {student.name},

                Your seating for the exam is:

                Classroom: {seating.block}
                Seat: {seating.seat}

                Kindly attend your examination on time.
                """
                msg = MIMEText(message)
                msg['Subject'] = "Exam Seating Details"
                msg['From'] = sender_email
                msg['To'] = student.email

                server.sendmail(sender_email, student.email, msg.as_string())

    return "Notifications sent successfully."

@app.route('/download', methods=['GET'])
def download():
    print("Download route triggered!")  # Debugging log

    # Query the seating plan from the database
    seating_data = SeatingPlan.query.all()

    # Create a DataFrame to store the data
    data = [{
        'Classroom': seat.classroom,
        'Seat': seat.seat,
        'Roll Number': seat.roll_number,
        'Name': seat.name
    } for seat in seating_data]
    df = pd.DataFrame(data)

    # Define the output file path
    output_file = os.path.join('downloads', 'seating_plan.xlsx')
    os.makedirs('downloads', exist_ok=True)
    df.to_excel(output_file, index=False)

    # Ensure file exists before sending
    if not os.path.exists(output_file):
        return "Error: File not found. Please try again.", 404

    # Serve the file to the user
    return send_file(output_file, as_attachment=True, download_name='seating_plan.xlsx')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

