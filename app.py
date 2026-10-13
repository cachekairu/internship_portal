import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-dito'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg2://postgres.ucahupeeiopqbsacqgex:0717marygracedizon@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)

# ----------------- DATABASE MODELS -----------------

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)

class Internship(db.Model):
    __tablename__ = 'internships'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    adviser_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    company_name = db.Column(db.String(150), nullable=False)
    required_hours = db.Column(db.Float, nullable=False)

class WeeklyLog(db.Model):
    __tablename__ = 'weekly_logs'
    id = db.Column(db.Integer, primary_key=True)
    internship_id = db.Column(db.Integer, db.ForeignKey('internships.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    hours_rendered = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Pending')

class Evaluation(db.Model):
    __tablename__ = 'evaluations'
    id = db.Column(db.Integer, primary_key=True)
    internship_id = db.Column(db.Integer, db.ForeignKey('internships.id'), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)

# ----------------- ROUTES -----------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'student')

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('May account na ang email na ito.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        new_user = User(name=name, email=email, password_hash=hashed_password, role=role)
        
        db.session.add(new_user)
        db.session.commit()

        flash('Matagumpay na nakapag-register! Mag-log in na.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            flash('Matagumpay na naka-log in!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Mali ang email o password. Subukan ulit.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        flash('Mag-log in muna.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    
    if user.role == 'student':
        internship = Internship.query.filter_by(student_id=user.id).first()

        if request.method == 'POST':
            if not internship:
                flash('Maglagay muna ng internship details bago mag-add ng log.', 'warning')
                return redirect(url_for('add_internship'))

            week_number = int(request.form.get('week_number'))
            hours_rendered = float(request.form.get('hours_rendered'))

            # I-check kung naisumite na ang week number na ito
            existing_log = WeeklyLog.query.filter_by(
                internship_id=internship.id, 
                week_number=week_number
            ).first()

            if existing_log:
                flash(f'Naka-submit na ang Week {week_number}. Hindi na ito pwedeng ulitin.', 'danger')
                return redirect(url_for('dashboard'))

            new_log = WeeklyLog(
                internship_id=internship.id,
                week_number=week_number,
                hours_rendered=hours_rendered,
                status='Pending'
            )
            db.session.add(new_log)
            db.session.commit()
            flash('Matagumpay na na-submit ang weekly log!', 'success')
            return redirect(url_for('dashboard'))

        total_hours = 0
        progress_percentage = 0
        logs = []
        eval_record = None

        if internship:
            logs = WeeklyLog.query.filter_by(internship_id=internship.id).all()
            approved_logs = WeeklyLog.query.filter_by(internship_id=internship.id, status='Approved').all()
            total_hours = sum(log.hours_rendered for log in approved_logs)
            eval_record = Evaluation.query.filter_by(internship_id=internship.id).first()
            
            if internship.required_hours > 0:
                progress_percentage = min(round((total_hours / internship.required_hours) * 100, 1), 100)

        return render_template(
            'dashboard.html',
            user=user,
            internship=internship,
            total_hours=total_hours,
            progress_percentage=progress_percentage,
            logs=logs,
            eval_record=eval_record
        )
    else:
        return render_template('dashboard.html', user=user)

@app.route('/logout')
def logout():
    session.clear()
    flash('Naka-log out na.', 'info')
    return redirect(url_for('login'))

@app.route('/add-internship', methods=['GET', 'POST'])
def add_internship():
    if 'user_id' not in session or session.get('user_role') != 'student':
        flash('Bawal dito.', 'danger')
        return redirect(url_for('login'))

    existing_internship = Internship.query.filter_by(student_id=session['user_id']).first()
    if existing_internship:
        flash('Mayroon ka nang rehistradong internship details.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        company_name = request.form.get('company_name')
        required_hours = float(request.form.get('required_hours'))
        adviser_id = int(request.form.get('adviser_id'))

        new_internship = Internship(
            student_id=session['user_id'],
            adviser_id=adviser_id,
            company_name=company_name,
            required_hours=required_hours
        )
        db.session.add(new_internship)
        db.session.commit()
        flash('Na-save na ang internship details!', 'success')
        return redirect(url_for('dashboard'))

    advisers = User.query.filter_by(role='adviser').all()
    return render_template('add_internship.html', advisers=advisers)

@app.route('/add-log', methods=['GET', 'POST'])
def add_log():
    if 'user_id' not in session or session.get('user_role') != 'student':
        flash('Bawal dito.', 'danger')
        return redirect(url_for('login'))

    internship = Internship.query.filter_by(student_id=session['user_id']).first()
    if not internship:
        flash('Maglagay muna ng internship details.', 'warning')
        return redirect(url_for('add_internship'))

    if request.method == 'POST':
        week_number = int(request.form.get('week_number'))
        hours_rendered = float(request.form.get('hours_rendered'))

        new_log = WeeklyLog(
            internship_id=internship.id,
            week_number=week_number,
            hours_rendered=hours_rendered,
            status='Pending'
        )
        db.session.add(new_log)
        db.session.commit()
        flash('Na-submit na ang weekly log!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('add_log.html')

@app.route('/review-logs', methods=['GET', 'POST'])
def review_logs():
    if 'user_id' not in session or session.get('user_role') != 'adviser':
        flash('Bawal dito.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        log_id = int(request.form.get('log_id'))
        status = request.form.get('status')
        log = WeeklyLog.query.get_or_404(log_id)
        log.status = status
        db.session.commit()
        flash('Na-update na ang status ng log!', 'success')
        return redirect(url_for('review_logs'))

    # I-join ang WeeklyLog, Internship, at User (Student) table para makuha ang pangalan at kumpanya
    logs = db.session.query(WeeklyLog, User, Internship).\
        join(Internship, WeeklyLog.internship_id == Internship.id).\
        join(User, Internship.student_id == User.id).\
        filter(Internship.adviser_id == session['user_id']).all()

    return render_template('review_logs.html', logs=logs)

@app.route('/evaluations', methods=['GET', 'POST'])
def evaluations():
    if 'user_id' not in session:
        flash('Mag-log in muna.', 'danger')
        return redirect(url_for('login'))

    user_role = session.get('user_role')
    user_id = session.get('user_id')

    if request.method == 'POST':
        if user_role != 'adviser':
            flash('Bawal mag-upload ang estudyante.', 'danger')
            return redirect(url_for('evaluations'))

        internship_id = request.form.get('internship_id')
        file = request.files.get('evaluation_file')

        if not internship_id:
            flash('Pumili muna ng estudyante.', 'warning')
            return redirect(url_for('evaluations'))

        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"internship_{internship_id}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                existing_eval = Evaluation.query.filter_by(internship_id=internship_id).first()
                if existing_eval:
                    existing_eval.file_path = file_path
                else:
                    new_eval = Evaluation(internship_id=internship_id, file_path=file_path)
                    db.session.add(new_eval)

                db.session.commit()
                flash('Matagumpay na na-upload ang evaluation form para sa estudyante!', 'success')
            else:
                flash('Invalid file format. PDF o Word document lang ang pwede.', 'danger')
        else:
            flash('Walang napiling file.', 'danger')

        return redirect(url_for('evaluations'))

    if user_role == 'student':
        internship = Internship.query.filter_by(student_id=user_id).first()
        eval_record = Evaluation.query.filter_by(internship_id=internship.id).first() if internship else None
        return render_template('evaluations.html', eval_record=eval_record, user_role=user_role)
    else:
        internships = Internship.query.filter_by(adviser_id=user_id).all()
        evals = Evaluation.query.join(Internship).filter(Internship.adviser_id == user_id).all()
        return render_template('evaluations.html', internships=internships, evals=evals, user_role=user_role)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)