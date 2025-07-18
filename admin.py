from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
import bcrypt
import logging
from functools import wraps
import csv
from io import StringIO
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'supersecretkey')  # Load secret key from .env, with fallback
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True for HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Enable logging
logging.basicConfig(level=logging.DEBUG)

# SQLAlchemy setup
Base = declarative_base()
# Construct database URL from environment variables
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_host = os.getenv('DB_HOST')
db_name = os.getenv('DB_NAME')
db_url = f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_name}'
engine = create_engine(db_url)
Session = sessionmaker(bind=engine)

# SQLAlchemy Models
class AdminUser(Base):
    __tablename__ = 'admin_users'
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

class Candidate(Base):
    __tablename__ = 'candidates'
    id = Column(Integer, primary_key=True)
    full_name = Column(String(100))
    email = Column(String(100))
    phone = Column(String(20))
    city = Column(String(50))
    position = Column(String(100))
    has_experience = Column(Boolean)
    years_experience = Column(Integer)
    tech_stack = Column(String(255))
    submitted_at = Column(DateTime)

class Score(Base):
    __tablename__ = 'scores'
    score_id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'))
    attempt_number = Column(Integer)
    total_questions = Column(Integer)
    correct_answers = Column(Integer)
    score_percent = Column(Float)
    submitted_at = Column(DateTime)

class Question(Base):
    __tablename__ = 'questions'
    question_id = Column(Integer, primary_key=True)
    set_number = Column(Integer)
    category = Column(String(50))
    question_text = Column(String(500))
    option_a = Column(String(255))
    option_b = Column(String(255))
    option_c = Column(String(255))
    option_d = Column(String(255))
    correct_option = Column(String(1))

class Answer(Base):
    __tablename__ = 'answers'
    answer_id = Column(Integer, primary_key=True)
    score_id = Column(Integer, ForeignKey('scores.score_id'))
    question_id = Column(Integer, ForeignKey('questions.question_id'))
    selected_option = Column(String(1))
    is_correct = Column(Boolean)
    answered_at = Column(DateTime)

# Decorator to enforce login requirement
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            session.clear()
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/', methods=['GET', 'POST'])
def login():
    if session.get('admin_logged_in'):
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            error = "Username and password are required."
        else:
            try:
                password = password.encode('utf-8')
                db_session = Session()
                admin_user = db_session.query(AdminUser).filter_by(username=username).first()
                if admin_user and bcrypt.checkpw(password, admin_user.password_hash.encode()):
                    session['admin_logged_in'] = True
                    db_session.close()
                    return redirect(url_for('dashboard'))
                else:
                    error = "Invalid credentials. Please try again."
                db_session.close()
            except Exception as e:
                app.logger.error(f"Login error: {str(e)}")
                error = "Database connection error. Please try again later."
    return render_template('login.html', error=error)

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/view_candidates')
@login_required
def view_candidates():
    try:
        db_session = Session()
        candidates = db_session.query(Candidate).all()
        db_session.close()
        return render_template('candidates.html', candidates=candidates)
    except Exception as e:
        app.logger.error(f"View candidates error: {str(e)}")
        flash('Error loading candidates. Please try again later.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/download_candidates_csv')
@login_required
def download_candidates_csv():
    try:
        db_session = Session()
        candidates = db_session.query(Candidate).order_by(Candidate.submitted_at.desc()).all()
        db_session.close()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Candidate ID',
            'Full Name',
            'Email',
            'Phone',
            'City',
            'Position',
            'Has Experience',
            'Years of Experience',
            'Tech Stack',
            'Submission Date'
        ])
        for candidate in candidates:
            writer.writerow([
                candidate.id,
                candidate.full_name,
                candidate.email,
                candidate.phone if candidate.phone else 'N/A',
                candidate.city if candidate.city else 'N/A',
                candidate.position if candidate.position else 'N/A',
                'Yes' if candidate.has_experience else 'No',
                candidate.years_experience if candidate.years_experience else 'N/A',
                candidate.tech_stack if candidate.tech_stack else 'N/A',
                candidate.submitted_at.strftime('%Y-%m-%d %I:%M:%S %p IST') if candidate.submitted_at else 'N/A'
            ])
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = 'attachment; filename=candidates.csv'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        app.logger.error(f"Download candidates CSV error: {str(e)}")
        flash('Error downloading candidates data. Please try again later.', 'danger')
        return redirect(url_for('view_candidates'))

@app.route('/view_scores')
@login_required
def view_scores():
    try:
        db_session = Session()
        # Get candidate count
        candidate_count = db_session.query(Candidate).count()
        
        # Get latest candidates and their scores
        candidates = {}
        all_candidates = db_session.query(Candidate).all()
        for candidate in all_candidates:
            email = candidate.email
            if email not in candidates:
                candidates[email] = {
                    'candidate_id': candidate.id,
                    'full_name': candidate.full_name,
                    'email': email,
                    'total_attempts': db_session.query(Candidate).filter_by(email=email).count(),
                    'attempts': []
                }
        
        scores = db_session.query(Score).join(Candidate).order_by(Candidate.email, Score.submitted_at).all()
        for score in scores:
            candidate = db_session.query(Candidate).filter_by(id=score.candidate_id).first()
            if candidate:
                candidates[candidate.email]['attempts'].append({
                    'score_id': score.score_id,
                    'attempt_number': score.attempt_number,
                    'total_questions': score.total_questions,
                    'correct_answers': score.correct_answers,
                    'score_percent': score.score_percent,
                    'submitted_at': score.submitted_at
                })
        
        for email in candidates:
            attempts = candidates[email]['attempts']
            attempts.sort(key=lambda x: x['submitted_at'])
            for i, attempt in enumerate(attempts, start=1):
                attempt['attempt_number'] = i
        
        db_session.close()
        return render_template('scores.html', candidates=list(candidates.values()))
    except Exception as e:
        app.logger.error(f"View scores error: {str(e)}")
        flash('Error loading scores. Please try again later.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/view_scores_by_set', methods=['GET', 'POST'])
@login_required
def view_scores_by_set():
    try:
        db_session = Session()
        sets = [q.set_number for q in db_session.query(Question.set_number).distinct().order_by(Question.set_number).all()]
        selected_set = request.form.get('set_number', sets[0] if sets else None)
        if selected_set:
            selected_set = int(selected_set)
        if not sets:
            db_session.close()
            return render_template('scores_by_set.html', sets=sets, selected_set=None, scores=[])
        
        scores = db_session.query(Score, Candidate, Question.set_number).\
            join(Candidate, Score.candidate_id == Candidate.id).\
            join(Answer, Answer.score_id == Score.score_id).\
            join(Question, Answer.question_id == Question.question_id).\
            filter(Question.set_number == selected_set).\
            group_by(Score.score_id, Candidate.id, Question.set_number).\
            order_by(Candidate.email, Score.attempt_number).all()
        
        scores = [{
            'candidate_id': score.Candidate.id,
            'full_name': score.Candidate.full_name,
            'email': score.Candidate.email,
            'score_id': score.Score.score_id,
            'attempt_number': score.Score.attempt_number,
            'total_questions': score.Score.total_questions,
            'correct_answers': score.Score.correct_answers,
            'score_percent': score.Score.score_percent,
            'submitted_at': score.Score.submitted_at,
            'set_number': score.set_number
        } for score in scores]
        
        db_session.close()
        return render_template('scores_by_set.html', sets=sets, selected_set=selected_set, scores=scores)
    except Exception as e:
        app.logger.error(f"View scores by set error: {str(e)}")
        flash('Error loading scores by set. Please try again later.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/view_answers_by_set/<int:score_id>')
@login_required
def view_answers_by_set(score_id):
    try:
        db_session = Session()
        score = db_session.query(Score, Candidate, Question.set_number).\
            join(Candidate, Score.candidate_id == Candidate.id).\
            join(Answer, Answer.score_id == Score.score_id).\
            join(Question, Answer.question_id == Question.question_id).\
            filter(Score.score_id == score_id).\
            group_by(Score.score_id, Candidate.id, Question.set_number).first()
        
        if not score:
            db_session.close()
            flash('Score not found.', 'danger')
            return redirect(url_for('view_scores_by_set'))
        
        score_dict = {
            'candidate_id': score.Candidate.id,
            'full_name': score.Candidate.full_name,
            'email': score.Candidate.email,
            'score_id': score.Score.score_id,
            'attempt_number': score.Score.attempt_number,
            'total_questions': score.Score.total_questions,
            'correct_answers': score.Score.correct_answers,
            'score_percent': score.Score.score_percent,
            'submitted_at': score.Score.submitted_at,
            'set_number': score.set_number
        }
        
        answers = db_session.query(Answer, Question).\
            join(Question, Answer.question_id == Question.question_id).\
            filter(Answer.score_id == score_id).\
            order_by(Question.category, Question.question_id).all()
        
        answers = [{
            'answer_id': answer.Answer.answer_id,
            'selected_option': answer.Answer.selected_option,
            'is_correct': answer.Answer.is_correct,
            'answered_at': answer.Answer.answered_at,
            'question_id': answer.Question.question_id,
            'set_number': answer.Question.set_number,
            'category': answer.Question.category,
            'question_text': answer.Question.question_text,
            'option_a': answer.Question.option_a,
            'option_b': answer.Question.option_b,
            'option_c': answer.Question.option_c,
            'option_d': answer.Question.option_d,
            'correct_option': answer.Question.correct_option
        } for answer in answers]
        
        db_session.close()
        return render_template('view_answers_by_set.html', score=score_dict, answers=answers)
    except Exception as e:
        app.logger.error(f"View answers by set error: {str(e)}")
        flash('Error loading answers. Please try again later.', 'danger')
        return redirect(url_for('view_scores_by_set'))

@app.route('/view_answers/<int:score_id>')
@login_required
def view_answers(score_id):
    try:
        db_session = Session()
        score = db_session.query(Score, Candidate, Question.set_number).\
            join(Candidate, Score.candidate_id == Candidate.id).\
            join(Answer, Answer.score_id == Score.score_id).\
            join(Question, Answer.question_id == Question.question_id).\
            filter(Score.score_id == score_id).\
            group_by(Score.score_id, Candidate.id, Question.set_number).first()
        
        if not score:
            db_session.close()
            flash('Score not found.', 'danger')
            return redirect(url_for('view_scores'))
        
        score_dict = {
            'candidate_id': score.Candidate.id,
            'full_name': score.Candidate.full_name,
            'email': score.Candidate.email,
            'score_id': score.Score.score_id,
            'attempt_number': score.Score.attempt_number,
            'total_questions': score.Score.total_questions,
            'correct_answers': score.Score.correct_answers,
            'score_percent': score.Score.score_percent,
            'submitted_at': score.Score.submitted_at,
            'set_number': score.set_number
        }
        
        answers = db_session.query(Answer, Question).\
            join(Question, Answer.question_id == Question.question_id).\
            filter(Answer.score_id == score_id).\
            order_by(Question.category, Question.question_id).all()
        
        answers = [{
            'answer_id': answer.Answer.answer_id,
            'selected_option': answer.Answer.selected_option,
            'is_correct': answer.Answer.is_correct,
            'answered_at': answer.Answer.answered_at,
            'question_id': answer.Question.question_id,
            'set_number': answer.Question.set_number,
            'category': answer.Question.category,
            'question_text': answer.Question.question_text,
            'option_a': answer.Question.option_a,
            'option_b': answer.Question.option_b,
            'option_c': answer.Question.option_c,
            'option_d': answer.Question.option_d,
            'correct_option': answer.Question.correct_option
        } for answer in answers]
        
        db_session.close()
        return render_template('view_answers.html', score=score_dict, answers=answers)
    except Exception as e:
        app.logger.error(f"View answers error: {str(e)}")
        flash('Error loading answers. Please try again later.', 'danger')
        return redirect(url_for('view_scores'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/test')
@login_required
def test():
    return "Admin app is working!"

if __name__ == '__main__':
    print("Starting Flask Admin Application on port 5001...")
    app.run(debug=True, host='0.0.0.0', port=5001)