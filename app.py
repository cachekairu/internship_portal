import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-dito'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg2://postgres.ucahupeeiopqbsacqgex:0717marygracedizon@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)

COURSE_HOURS = {
    'BSIT': 480,
    'BSCS': 480,
    'BSIS': 400,
    'BPA': 300
}

# ----------------- DATABASE MODELS -----------------

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    student_number = db.Column(db.String(50), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'student', 'adviser', 'admin'
    course = db.Column(db.String(50), nullable=True)

class Internship(db.Model):
    __tablename__ = 'internships'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    adviser_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    company_name = db.Column(db.String(150), nullable=False)
    required_hours = db.Column(db.Float, nullable=False)
    moa_path = db.Column(db.String(255), nullable=True) # MOA / Company document file path
    status = db.Column(db.String(20), default='Pending') # 'Pending', 'Approved', 'Rejected'

class WeeklyLog(db.Model):
    __tablename__ = 'weekly_logs'
    id = db.Column(db.Integer, primary_key=True)
    internship_id = db.Column(db.Integer, db.ForeignKey('internships.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    hours_rendered = db.Column(db.Float, nullable=False)
    time_card_path = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='Pending')

class Evaluation(db.Model):
    __tablename__ = 'evaluations'
    id = db.Column(db.Integer, primary_key=True)
    internship_id = db.Column(db.Integer, db.ForeignKey('internships.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    remarks = db.Column(db.Text, nullable=True)


# ----------------- ROUTES -----------------

@app.route('/')
def index():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['POST'])
def register():
    name = request.form.get('name', '').strip()
    student_number = request.form.get('student_number', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    course = request.form.get('course', '').strip()
    role = 'student'

    if not re.match(r"^[A-Za-z\s]+$", name):
        flash('Full Name must contain letters only.', 'danger')
        return render_template('login.html', active_tab='register')

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        flash('Email already registered.', 'danger')
        return render_template('login.html', active_tab='register')

    hashed_password = generate_password_hash(password)
    new_user = User(
        name=name,
        student_number=student_number,
        email=email,
        password_hash=hashed_password,
        role=role,
        course=course
    )
    
    db.session.add(new_user)
    db.session.commit()

    flash('Successfully registered! Please log in.', 'success')
    return render_template('login.html', active_tab='login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            flash('Successfully logged in!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
            return render_template('login.html', active_tab='login')

    return render_template('login.html', active_tab='login')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if user.role == 'student':
        internship = Internship.query.filter_by(student_id=user.id).first()

        if request.method == 'POST':
            if not internship or internship.status != 'Approved':
                flash('Your internship request must be approved by your adviser first before submitting logs.', 'warning')
                return redirect(url_for('dashboard'))

            hours_rendered = float(request.form.get('hours_rendered'))
            existing_logs_count = WeeklyLog.query.filter_by(internship_id=internship.id).count()
            next_week_number = existing_logs_count + 1

            time_card_path = None
            file = request.files.get('time_card_file')
            if file and file.filename != '':
                if allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"student_{user.id}_week_{next_week_number}_{filename}"
                    time_card_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(time_card_path)

            new_log = WeeklyLog(
                internship_id=internship.id,
                week_number=next_week_number,
                hours_rendered=hours_rendered,
                time_card_path=time_card_path,
                status='Pending'
            )
            db.session.add(new_log)
            db.session.commit()
            flash(f'Successfully submitted Week {next_week_number} log!', 'success')
            return redirect(url_for('dashboard'))

        total_hours = 0
        progress_percentage = 0
        logs = []
        eval_records = []

        if internship and internship.status == 'Approved':
            logs = WeeklyLog.query.filter_by(internship_id=internship.id).order_by(WeeklyLog.week_number.asc()).all()
            approved_logs = WeeklyLog.query.filter_by(internship_id=internship.id, status='Approved').all()
            total_hours = sum(log.hours_rendered for log in approved_logs)
            eval_records = Evaluation.query.filter_by(internship_id=internship.id).all()
            
            if internship.required_hours > 0:
                progress_percentage = min(round((total_hours / internship.required_hours) * 100, 1), 100)

        next_week = len(logs) + 1

        return render_template(
            'dashboard.html',
            user=user,
            internship=internship,
            total_hours=total_hours,
            progress_percentage=progress_percentage,
            logs=logs,
            eval_records=eval_records,
            next_week=next_week
        )
    elif user.role == 'adviser':
        search_query = request.args.get('search_query', '').strip()
        pending_requests_count = Internship.query.filter_by(adviser_id=user.id, status='Pending').count()
        
        pending_logs_count = db.session.query(WeeklyLog).\
            join(Internship, WeeklyLog.internship_id == Internship.id).\
            filter(Internship.adviser_id == user.id, WeeklyLog.status == 'Pending').count()

        query = db.session.query(User, Internship).\
            join(Internship, User.id == Internship.student_id).\
            filter(Internship.adviser_id == user.id, Internship.status == 'Approved')
        
        if search_query:
            query = query.filter(
                db.or_(
                    User.name.ilike(f"%{search_query}%"),
                    User.student_number.ilike(f"%{search_query}%")
                )
            )
        raw_students = query.all()
        
        students = []
        for student, internship in raw_students:
            approved_logs = WeeklyLog.query.filter_by(internship_id=internship.id, status='Approved').all()
            total_hours = sum(log.hours_rendered for log in approved_logs)
            students.append({
                'student': student,
                'internship': internship,
                'total_hours': total_hours
            })

        return render_template('dashboard.html', user=user, students=students, pending_requests_count=pending_requests_count, pending_logs_count=pending_logs_count)
    else:
        return redirect(url_for('admin_users'))

@app.route('/requests', methods=['GET', 'POST'])
def requests_page():
    if 'user_id' not in session or session.get('user_role') != 'adviser':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        internship_id = request.form.get('internship_id')
        action_status = request.form.get('status')
        if internship_id and action_status:
            target_internship = Internship.query.get_or_404(int(internship_id))
            target_internship.status = action_status
            db.session.commit()
            flash(f'Internship request status updated to {action_status}!', 'success')
            return redirect(url_for('requests_page'))

    pending_requests_count = Internship.query.filter_by(adviser_id=user.id, status='Pending').count()
    pending_logs_count = db.session.query(WeeklyLog).\
        join(Internship, WeeklyLog.internship_id == Internship.id).\
        filter(Internship.adviser_id == user.id, WeeklyLog.status == 'Pending').count()
        
    pending_query = db.session.query(User, Internship).\
        join(Internship, User.id == Internship.student_id).\
        filter(Internship.adviser_id == user.id, Internship.status == 'Pending')
    pending_requests = pending_query.all()

    return render_template('requests.html', user=user, pending_requests=pending_requests, pending_requests_count=pending_requests_count, pending_logs_count=pending_logs_count)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/add-internship', methods=['GET', 'POST'])
def add_internship():
    if 'user_id' not in session or session.get('user_role') != 'student':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    existing_internship = Internship.query.filter_by(student_id=session['user_id']).first()
    if existing_internship:
        flash('You already have registered practicum details.', 'warning')
        return redirect(url_for('dashboard'))

    student = User.query.get(session['user_id'])

    if request.method == 'POST':
        company_name = request.form.get('company_name')
        adviser_id = int(request.form.get('adviser_id'))
        required_hours = COURSE_HOURS.get(student.course, 480)

        moa_path = None
        file = request.files.get('moa_file')
        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"student_{student.id}_moa_{filename}"
                moa_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(moa_path)

        new_internship = Internship(
            student_id=student.id,
            adviser_id=adviser_id,
            company_name=company_name,
            required_hours=required_hours,
            moa_path=moa_path,
            status='Pending'
        )
        db.session.add(new_internship)
        db.session.commit()
        flash('Practicum details submitted successfully! Waiting for adviser approval.', 'success')
        return redirect(url_for('dashboard'))

    advisers = User.query.filter_by(role='adviser').all()
    return render_template('add_internship.html', advisers=advisers, student=student)

@app.route('/review-logs', methods=['GET', 'POST'])
def review_logs():
    if 'user_id' not in session or session.get('user_role') != 'adviser':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        log_id = int(request.form.get('log_id'))
        status = request.form.get('status')
        log = WeeklyLog.query.get_or_404(log_id)
        
        internship = Internship.query.get(log.internship_id)
        max_week_record = WeeklyLog.query.filter_by(internship_id=internship.id).order_by(WeeklyLog.week_number.desc()).first()
        max_week = max_week_record.week_number if max_week_record else 0
        allowed_min_week = max_week - 2

        if log.status == 'Pending' or log.week_number >= allowed_min_week:
            log.status = status
            db.session.commit()
            flash('Log status updated successfully!', 'success')
        else:
            flash("You can only approve or reject logs that are within the 3 recent weeks.", "danger")
            
        return redirect(url_for('review_logs'))

    company_filter = request.args.get('company', '')
    week_filter = request.args.get('week', '')
    status_filter = request.args.get('status', '')
    search_query = request.args.get('search', '')
    sort_order = request.args.get('sort', 'latest')

    query = db.session.query(WeeklyLog, User, Internship).\
        join(Internship, WeeklyLog.internship_id == Internship.id).\
        join(User, Internship.student_id == User.id).\
        filter(Internship.adviser_id == session['user_id'])

    if company_filter:
        query = query.filter(Internship.company_name.ilike(f"%{company_filter}%"))
    if week_filter:
        query = query.filter(WeeklyLog.week_number == int(week_filter))
    if status_filter:
        query = query.filter(WeeklyLog.status == status_filter)
    if search_query:
        query = query.filter(User.name.ilike(f"%{search_query}%"))

    if sort_order == 'oldest':
        query = query.order_by(WeeklyLog.id.asc())
    else:
        query = query.order_by(WeeklyLog.id.desc())

    logs = query.all()
    companies = db.session.query(Internship.company_name).filter_by(adviser_id=session['user_id']).distinct().all()
    pending_requests_count = Internship.query.filter_by(adviser_id=session['user_id'], status='Pending').count()
    pending_logs_count = db.session.query(WeeklyLog).\
        join(Internship, WeeklyLog.internship_id == Internship.id).\
        filter(Internship.adviser_id == session['user_id'], WeeklyLog.status == 'Pending').count()

    return render_template('review_logs.html', logs=logs, companies=companies, pending_requests_count=pending_requests_count, pending_logs_count=pending_logs_count)

@app.route('/evaluations/<int:internship_id>', methods=['GET', 'POST'])
def evaluations(internship_id):
    if 'user_id' not in session:
        flash('Please log in first.', 'danger')
        return redirect(url_for('login'))

    user_role = session.get('user_role')
    user_id = session.get('user_id')

    internship = Internship.query.get_or_404(internship_id)
    student = User.query.get_or_404(internship.student_id)

    if user_role == 'adviser' and internship.adviser_id != user_id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))

    if user_role == 'student' and internship.student_id != user_id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        log_id = request.form.get('log_id')
        if log_id:
            if user_role != 'adviser':
                flash('Unauthorized action.', 'danger')
                return redirect(url_for('evaluations', internship_id=internship_id))
            
            status = request.form.get('status')
            log_item = WeeklyLog.query.get_or_404(int(log_id))
            
            max_week_record = WeeklyLog.query.filter_by(internship_id=internship.id).order_by(WeeklyLog.week_number.desc()).first()
            max_week = max_week_record.week_number if max_week_record else 0
            allowed_min_week = max_week - 2

            if log_item.status == 'Pending' or log_item.week_number >= allowed_min_week:
                log_item.status = status
                db.session.commit()
                flash(f'Weekly log status updated to {status}!', 'success')
            else:
                flash("You can only approve or reject logs that are within the 3 recent weeks.", "danger")
                
            return redirect(url_for('evaluations', internship_id=internship_id))

        if user_role != 'adviser':
            flash('Students are not allowed to upload.', 'danger')
            return redirect(url_for('evaluations', internship_id=internship_id))

        eval_id = request.form.get('eval_id')
        remarks = request.form.get('remarks')
        file = request.files.get('evaluation_file')

        if eval_id:
            existing_eval = Evaluation.query.get_or_404(int(eval_id))
            existing_eval.remarks = remarks
            if file and file.filename != '':
                if allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"eval_intern_{internship_id}_week_{existing_eval.week_number}_{filename}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    existing_eval.file_path = file_path
            db.session.commit()
            flash('Evaluation updated successfully!', 'success')
        else:
            existing_evals_count = Evaluation.query.filter_by(internship_id=internship_id).count()
            next_eval_week = existing_evals_count + 1

            if file and file.filename != '':
                if allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"eval_intern_{internship_id}_week_{next_eval_week}_{filename}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)

                    new_eval = Evaluation(
                        internship_id=internship_id,
                        week_number=next_eval_week,
                        file_path=file_path,
                        remarks=remarks
                    )
                    db.session.add(new_eval)
                    db.session.commit()
                    flash(f'Weekly evaluation for Week {next_eval_week} uploaded successfully!', 'success')
                else:
                    flash('Invalid file format.', 'danger')
            else:
                flash('No file selected.', 'danger')

        return redirect(url_for('evaluations', internship_id=internship_id))

    eval_records = Evaluation.query.filter_by(internship_id=internship_id).order_by(Evaluation.week_number.asc()).all()
    next_eval_week = len(eval_records) + 1

    logs = WeeklyLog.query.filter_by(internship_id=internship.id).order_by(WeeklyLog.week_number.asc()).all()
    approved_logs = WeeklyLog.query.filter_by(internship_id=internship.id, status='Approved').all()
    total_hours = sum(log.hours_rendered for log in approved_logs)
    progress_percentage = 0
    if internship.required_hours > 0:
        progress_percentage = min(round((total_hours / internship.required_hours) * 100, 1), 100)

    max_week_record = WeeklyLog.query.filter_by(internship_id=internship.id).order_by(WeeklyLog.week_number.desc()).first()
    max_week = max_week_record.week_number if max_week_record else 0
    allowed_min_week = max_week - 2
    pending_requests_count = Internship.query.filter_by(adviser_id=user_id, status='Pending').count() if user_role == 'adviser' else 0
    pending_logs_count = db.session.query(WeeklyLog).\
        join(Internship, WeeklyLog.internship_id == Internship.id).\
        filter(Internship.adviser_id == user_id, WeeklyLog.status == 'Pending').count() if user_role == 'adviser' else 0

    return render_template(
        'evaluations.html', 
        internship=internship, 
        student=student, 
        eval_records=eval_records, 
        next_eval_week=next_eval_week, 
        user_role=user_role,
        logs=logs,
        total_hours=total_hours,
        progress_percentage=progress_percentage,
        allowed_min_week=allowed_min_week,
        pending_requests_count=pending_requests_count,
        pending_logs_count=pending_logs_count
    )


# ----------------- ADMIN MANAGEMENT & FULL ACCESS ROUTES -----------------

@app.route('/admin/users')
def admin_users():
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
    
    advisers = User.query.filter_by(role='adviser').all()
    admins = User.query.filter_by(role='admin').all()
    
    return render_template('admin_users.html', advisers=advisers, admins=admins)

@app.route('/admin/users/add', methods=['GET', 'POST'])
def admin_add_user():
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        student_number = request.form.get('student_number', '').strip()
        course = request.form.get('course', '').strip()
        role = request.form.get('role', '').strip()
        password = request.form.get('password', '').strip()
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered.', 'danger')
            return redirect(url_for('admin_add_user'))
            
        hashed_password = generate_password_hash(password)
        new_user = User(
            name=name,
            email=email,
            student_number=student_number if student_number else None,
            course=course if course else None,
            role=role,
            password_hash=hashed_password
        )
        
        db.session.add(new_user)
        db.session.commit()
        flash('New user added successfully!', 'success')
        return redirect(url_for('admin_users'))
        
    return render_template('admin_add_user.html')

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
def admin_edit_user(user_id):
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
    
    target_user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        target_user.name = request.form.get('name', '').strip()
        target_user.email = request.form.get('email', '').strip()
        target_user.student_number = request.form.get('student_number', '').strip() or None
        target_user.course = request.form.get('course', '').strip() or None
        target_user.role = request.form.get('role', '').strip()
        
        password = request.form.get('password', '').strip()
        if password:
            target_user.password_hash = generate_password_hash(password)
            
        db.session.commit()
        flash('User account updated successfully!', 'success')
        return redirect(url_for('admin_edit_user', user_id=user_id))
        
    internship = None
    logs = []
    advisers = []
    assigned_students = []

    if target_user.role == 'student':
        internship = Internship.query.filter_by(student_id=target_user.id).first()
        if internship:
            logs = WeeklyLog.query.filter_by(internship_id=internship.id).order_by(WeeklyLog.week_number.asc()).all()
        advisers = User.query.filter_by(role='adviser').all()
    elif target_user.role == 'adviser':
        raw_students = db.session.query(User, Internship).\
            join(Internship, User.id == Internship.student_id).\
            filter(Internship.adviser_id == target_user.id).all()
        for student, intern in raw_students:
            assigned_students.append({'student': student, 'internship': intern})

    return render_template(
        'admin_edit_user.html',
        target_user=target_user,
        internship=internship,
        logs=logs,
        advisers=advisers,
        assigned_students=assigned_students
    )

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
def admin_delete_user(user_id):
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
        
    target_user = User.query.get_or_404(user_id)
    if target_user.id == session['user_id']:
        flash('You cannot delete your own admin account.', 'danger')
        return redirect(url_for('admin_users'))
        
    db.session.delete(target_user)
    db.session.commit()
    flash('User deleted successfully!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/internship/update/<int:internship_id>', methods=['POST'])
def admin_update_internship(internship_id):
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
        
    internship = Internship.query.get_or_404(internship_id)
    internship.company_name = request.form.get('company_name', '').strip()
    internship.required_hours = float(request.form.get('required_hours', 480))
    internship.status = request.form.get('status')
    internship.adviser_id = int(request.form.get('adviser_id'))
    
    db.session.commit()
    flash('Internship data updated successfully!', 'success')
    return redirect(url_for('admin_edit_user', user_id=internship.student_id))

@app.route('/admin/log/update/<int:log_id>', methods=['POST'])
def admin_update_log(log_id):
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
        
    log = WeeklyLog.query.get_or_404(log_id)
    log.hours_rendered = float(request.form.get('hours_rendered', 0))
    log.status = request.form.get('status')
    
    db.session.commit()
    internship = Internship.query.get(log.internship_id)
    flash('Weekly log updated successfully!', 'success')
    return redirect(url_for('admin_edit_user', user_id=internship.student_id))

@app.route('/admin/log/delete/<int:log_id>', methods=['POST'])
def admin_delete_log(log_id):
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
        
    log = WeeklyLog.query.get_or_404(log_id)
    internship = Internship.query.get(log.internship_id)
    db.session.delete(log)
    db.session.commit()
    flash('Weekly log deleted successfully!', 'success')
    return redirect(url_for('admin_edit_user', user_id=internship.student_id))

@app.route('/admin/internships')
def admin_internships():
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
        
    pending_internships = db.session.query(Internship, User).join(User, Internship.student_id == User.id).filter(Internship.status == 'Pending').all()
    students = User.query.filter_by(role='student').all()
    
    return render_template('admin_internships.html', pending_internships=pending_internships, students=students)

@app.route('/admin/internships/status/<int:internship_id>', methods=['POST'])
def admin_update_internship_status(internship_id):
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
        
    internship = Internship.query.get_or_404(internship_id)
    status = request.form.get('status')
    if status in ['Approved', 'Rejected', 'Pending']:
        internship.status = status
        db.session.commit()
        flash(f'Internship status updated to {status}!', 'success')
    return redirect(url_for('admin_internships'))

@app.route('/admin/internships/delete/<int:internship_id>', methods=['POST'])
def admin_delete_internship(internship_id):
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
        
    target_internship = Internship.query.get_or_404(internship_id)
    db.session.delete(target_internship)
    db.session.commit()
    flash('Internship record deleted successfully!', 'success')
    return redirect(url_for('admin_internships'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)