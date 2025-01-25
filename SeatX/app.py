from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import os
import smtplib
import random
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = 'your_secret_key' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///seatx.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
scheduler = BackgroundScheduler()
scheduler.start()

# Models

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    block = db.Column(db.String(50), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), nullable=False)
    student_class = db.Column(db.String(50), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    semester = db.Column(db.String(50), nullable=True)

class SeatingPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classroom = db.Column(db.String(100), nullable=False)
    seat = db.Column(db.String(50), nullable=False)
    roll_number = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)

class ExamConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_time = db.Column(db.String(100), nullable=False)

@app.route('/')
def index():
    return render_template('main_page.html')

@app.route('/home')
def home():
    return render_template('home.html')  

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html') 

@app.route('/dashboardinv')
def dashboard_inv():
    return render_template('dashboardinv.html')  

@app.route('/emergency.html')
def emergency():
    return render_template('emergency.html')


@app.route('/sign_up', methods=['GET', 'POST'])
def sign_up():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        print(f"Received: username={username}, email={email}, password={password}")

        if not username.isalnum():
            flash("Username can only contain letters and numbers.", "error")
            return redirect(url_for('sign_up'))

        if User.query.filter_by(email=email).first() or User.query.filter_by(username=username).first():
            print("Error: User already exists")
            flash("Account with this email or username already exists.", "error")
            return redirect(url_for('sign_up'))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        print(f"Hashed password: {hashed_password}")

        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        print("User created successfully")
        flash("Sign up successful. Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('sign_up.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if user exists in the database
        user = User.query.filter_by(username=username).first()

        if user:
            # Check if password matches
            if check_password_hash(user.password, password):
                session['user_id'] = user.id
                session['username'] = user.username
                flash(f"Welcome back, {user.username}!", "success")
                return redirect(url_for('home'))
            else:
                flash("Incorrect password. Please try again.", "error")
        else:
            flash("Username not found. Please sign up first.", "error")

        return redirect(url_for('login'))

    return render_template('login.html')



@app.route('/upload', methods=['POST'])
def upload():
    exam_time = request.form.get('exam_time')

    if not exam_time:
        return "Error: Examination time not provided.", 400

    db.session.query(ExamConfig).delete()
    db.session.add(ExamConfig(exam_time=exam_time))

    if 'classrooms' in request.files and 'students' in request.files:
        classrooms_file = request.files['classrooms']
        students_file = request.files['students']

        upload_dir = os.path.join('uploads')
        os.makedirs(upload_dir, exist_ok=True)

        classrooms_path = os.path.join(upload_dir, 'classrooms.xlsx')
        students_path = os.path.join(upload_dir, 'students.xlsx')

        classrooms_file.save(classrooms_path)
        students_file.save(students_path)

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
        return redirect(url_for('dashboard'))

    return "Error: Files not uploaded. Please try again."

def is_adjacent_violation(grid, row, col, student, relaxed=False):
    """Check adjacency constraints for seating."""
    adjacent_positions = [
        (row - 1, col),  # Above
        (row + 1, col),  # Below
        (row, col - 1),  # Left
        (row, col + 1)   # Right
    ]

    for adj_row, adj_col in adjacent_positions:
        if 0 <= adj_row < len(grid) and 0 <= adj_col < len(grid[0]):  # Ensure valid position
            adjacent_student = grid[adj_row][adj_col]
            if adjacent_student and adjacent_student.department == student.department and adjacent_student.semester == student.semester:
                if not relaxed:  # Strict mode
                    return True
                elif adj_row == row:  # Ignore vertical adjacency in relaxed mode
                    continue
                elif adj_col == col:  # Ignore horizontal adjacency in relaxed mode
                    continue

    return False


def backtrack_seating(grid, students, index, relaxed=False):
    """Recursive backtracking function for seating students."""
    if index >= len(students):  # Base case: All students are seated
        return True

    student = students[index]

    for row in range(len(grid)):
        for col in range(len(grid[0])):
            if grid[row][col] is None and not is_adjacent_violation(grid, row, col, student, relaxed):
                # Place the student
                grid[row][col] = student

                # Recurse to seat the next student
                if backtrack_seating(grid, students, index + 1, relaxed):
                    return True  # Found a valid arrangement

                # Undo the placement (backtrack)
                grid[row][col] = None

    return False  # No valid configuration found


@app.route('/generate_seating', methods=['POST'])
def generate_seating():
    classrooms = Classroom.query.all()
    students = Student.query.all()

    # Validate and shuffle students
    if not students:
        return "Error: No students available for seating.", 400

    random.shuffle(students)  # Randomize student order

    total_seats = sum([c.capacity for c in classrooms])
    if len(students) > total_seats:
        return f"Error: Not enough total seats available! {len(students)} students and only {total_seats} seats."

    seating_plan = []
    seat_columns = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']

    # Create a grid for all classrooms
    grid = []
    classroom_map = {}
    for classroom in classrooms:
        rows = (classroom.capacity + len(seat_columns) - 1) // len(seat_columns)
        classroom_map[classroom.name] = len(grid)
        grid.extend([[None for _ in range(len(seat_columns))] for _ in range(rows)])

    # Attempt to seat all students with strict constraints
    if not backtrack_seating(grid, list(students), 0, relaxed=False):
        # Relax constraints if strict seating fails
        print("Relaxing constraints to find a valid seating arrangement...")
        if not backtrack_seating(grid, list(students), 0, relaxed=True):
            return "Error: No valid seating arrangement found even after relaxing constraints."

    # Convert the grid to a seating plan
    student_index = 0
    for classroom in classrooms:
        start_row = classroom_map[classroom.name]
        for row in range(start_row, start_row + classroom.capacity // len(seat_columns)):
            for col in range(len(seat_columns)):
                if grid[row][col]:
                    student = grid[row][col]
                    seat_label = f"{seat_columns[col]}{row + 1}"
                    seating_plan.append({
                        'classroom': classroom.name,
                        'block': classroom.block,
                        'seat': seat_label,
                        'roll_number': student.roll_number,
                        'name': student.name
                    })
                    db.session.add(SeatingPlan(
                        classroom=classroom.name,
                        seat=seat_label,
                        roll_number=student.roll_number,
                        name=student.name
                    ))

    db.session.commit()
    return render_template('seating_plan.html', seating=seating_plan)

def send_email_notifications():
    with app.app_context():
        exam_config = ExamConfig.query.first()
        if not exam_config or not exam_config.exam_time:
            print("Error: Examination time not set.")
            return

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

                    Classroom: {seating.classroom}
                    Seat: {seating.seat}

                    Kindly attend your examination on time.
                    """
                    msg = MIMEText(message)
                    msg['Subject'] = "Exam Seating Details"
                    msg['From'] = sender_email
                    msg['To'] = student.email

                    server.sendmail(sender_email, student.email, msg.as_string())

@app.route('/send_notifications', methods=['POST'])
def schedule_notifications():
    exam_config = ExamConfig.query.first()
    if not exam_config or not exam_config.exam_time:
        return "Error: Examination time not set.", 400

    exam_time = datetime.strptime(exam_config.exam_time, "%Y-%m-%dT%H:%M")
    notify_time = exam_time - timedelta(minutes=30)

    scheduler.add_job(func=send_email_notifications, trigger='date', run_date=notify_time)

    return f"Notifications have been scheduled for {notify_time.strftime('%Y-%m-%d %H:%M')}"

@app.route('/upload_students', methods=['POST'])
def upload_students():
    if 'students_file' not in request.files:
        return "Error: No file uploaded.", 400

    file = request.files['students_file']
    if file.filename == '':
        return "Error: Empty file name.", 400

    if not (file.filename.endswith('.xlsx') or file.filename.endswith('.csv')):
        return "Error: Unsupported file format. Please upload a .xlsx or .csv file.", 400

    try:
        if file.filename.endswith('.xlsx'):
            data = pd.read_excel(file)
        else:
            data = pd.read_csv(file)

        if 'Roll Number' not in data.columns or 'Email' not in data.columns:
            return "Error: Required columns ('Roll Number' and 'Email') are missing in the file.", 400

        db.session.query(Student).delete()

        for _, row in data.iterrows():
            if pd.isna(row['Roll Number']) or pd.isna(row['Email']):
                continue

            student = Student(
                roll_number=row['Roll Number'],
                email=row['Email'],
                name='',
                student_class='',
                department='',
                semester=''
            )
            db.session.add(student)

        db.session.commit()
        return render_template('emergency.html', upload_success="Student data uploaded successfully!")

    except Exception as e:
        return render_template('emergency.html', upload_error=f"Error processing the file: {str(e)}")


@app.route('/send_emergency_notification', methods=['POST'])
def send_emergency_notification():
    # Get the message from the form
    message = request.form.get('message')
    
    # Check if the message is empty
    if not message:
        return "Error: Message content is empty.", 400

    # Prepare the email body
    email_body = f"This is an emergency notification\n\n{message}"

    # Query all student emails from the database
    students = Student.query.all()

    # Sender email credentials
    sender_email = "seatx.app@gmail.com"
    sender_password = "vugo bnrz eueb fakr"  # Replace with secure storage for credentials

    try:
        # Setup the email server
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)

            # Send email to each student
            for student in students:
                msg = MIMEText(email_body)
                msg['Subject'] = "Emergency Notification"
                msg['From'] = sender_email
                msg['To'] = student.email
                server.sendmail(sender_email, student.email, msg.as_string())

        return render_template('emergency.html', notification_success="Emergency notifications sent successfully!")


    except smtplib.SMTPException as e:
        return render_template('emergency.html', notification_error=f"Error sending notifications: {str(e)}")

@app.route('/download', methods=['GET'])
def download():
    seating_data = SeatingPlan.query.all()

    data = [{
        'Classroom': seat.classroom,
        'Seat': seat.seat,
        'Roll Number': seat.roll_number,
        'Name': seat.name
    } for seat in seating_data]
    df = pd.DataFrame(data)

    output_file = os.path.join('downloads', 'seating_plan.xlsx')
    os.makedirs('downloads', exist_ok=True)
    df.to_excel(output_file, index=False)

    if not os.path.exists(output_file):
        return "Error: File not found. Please try again.", 404

    return send_file(output_file, as_attachment=True, download_name='seating_plan.xlsx')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

