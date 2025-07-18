from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import re
from datetime import datetime
import traceback
import boto3
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'supersecretkey')  # Load secret key from .env, with fallback
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True for HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Test configuration
TEST_DURATION_MINUTES = 1  # Set test duration to 30 minutes

# AWS S3 configuration
S3_BUCKET = os.getenv('S3_BUCKET')  # Must be set in environment
S3_REGION = os.getenv('S3_REGION')  # Must be set in environment
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),  # Must be set in environment
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),  # Must be set in environment
    region_name=S3_REGION
)

# SQLAlchemy setup
Base = declarative_base()
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_host = os.getenv('DB_HOST')
db_name = os.getenv('DB_NAME')
db_url = f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_name}'
engine = create_engine(db_url)
Session = sessionmaker(bind=engine)

# SQLAlchemy Models
class Candidate(Base):
    __tablename__ = 'candidates'
    id = Column(Integer, primary_key=True)
    full_name = Column(String(100))
    email = Column(String(100))
    phone = Column(String(20))
    area = Column(String(100))
    city = Column(String(50))
    pincode = Column(String(10))
    position = Column(String(100))
    has_experience = Column(Boolean)
    previous_company = Column(String(100))
    role = Column(String(100))
    domain = Column(String(100))
    years_experience = Column(Float)
    tech_stack = Column(String(255))
    submitted_at = Column(DateTime)

class Question(Base):
    __tablename__ = 'questions'
    question_id = Column(Integer, primary_key=True)
    set_number = Column(Integer)
    question_text = Column(String(500))
    option_a = Column(String(255))
    option_b = Column(String(255))
    option_c = Column(String(255))
    option_d = Column(String(255))
    correct_option = Column(String(1))

class TestHistory(Base):
    __tablename__ = 'test_history'
    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'))
    question_id = Column(Integer, ForeignKey('questions.question_id'))
    attempt_number = Column(Integer)
    assigned_at = Column(DateTime)

class Answer(Base):
    __tablename__ = 'answers'
    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'))
    question_id = Column(Integer, ForeignKey('questions.question_id'))
    selected_option = Column(String(1))
    is_correct = Column(Boolean)
    answered_at = Column(DateTime)
    score_id = Column(Integer, ForeignKey('scores.score_id'))

class Score(Base):
    __tablename__ = 'scores'
    score_id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'))
    attempt_number = Column(Integer)
    total_questions = Column(Integer)
    correct_answers = Column(Integer)
    score_percent = Column(Float)
    submitted_at = Column(DateTime)

# ---------- UTILITY FUNCTIONS ----------
def validate_email(email): 
    return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email)

def validate_phone(phone): 
    return re.match(r'^\d{10}$', phone)

def validate_pincode(pincode): 
    return re.match(r'^\d{6}$', pincode)

# ---------- DATABASE HELPER FUNCTIONS ----------
def get_candidate_id_by_email(email):
    """Get the most recent candidate ID by email address"""
    try:
        db_session = Session()
        candidate = db_session.query(Candidate).filter(func.lower(Candidate.email) == func.lower(email.strip())).\
            order_by(Candidate.submitted_at.desc()).first()
        candidate_id = candidate.id if candidate else None
        print(f"Email {email} -> Most recent Candidate ID: {candidate_id}")
        return candidate_id
    except Exception as e:
        print(f"Error fetching candidate by email: {e}")
        traceback.print_exc()
        return None
    finally:
        db_session.close()

def get_all_candidate_ids_by_email(email):
    """Get all candidate IDs for an email address (for historical data)"""
    try:
        db_session = Session()
        candidates = db_session.query(Candidate).filter(func.lower(Candidate.email) == func.lower(email.strip())).\
            order_by(Candidate.submitted_at.asc()).all()
        candidate_ids = [candidate.id for candidate in candidates]
        print(f"Email {email} -> All Candidate IDs: {candidate_ids}")
        return candidate_ids
    except Exception as e:
        print(f"Error fetching all candidate IDs by email: {e}")
        traceback.print_exc()
        return []
    finally:
        db_session.close()

def get_attempt_number_for_email(email):
    """Get the total number of attempts (candidate records) for this email"""
    all_candidate_ids = get_all_candidate_ids_by_email(email)
    attempt_number = len(all_candidate_ids)
    print(f"Email {email} has {attempt_number} total attempts")
    return attempt_number

def insert_candidate(data):
    """Insert new candidate into database - ALWAYS creates a new record"""
    try:
        db_session = Session()
        candidate = Candidate(
            full_name=data["full_name"],
            email=data["email"],
            phone=data["phone"],
            area=data["address"]["area"],
            city=data["address"]["city"],
            pincode=data["address"]["pincode"],
            position=data["position"],
            has_experience=data["experience"]["has_experience"],
            previous_company=data["experience"]["previous_company"],
            role=data["experience"]["role"],
            domain=data["experience"]["domain"],
            years_experience=data["experience"]["years_experience"],
            tech_stack=",".join(data["tech_stack"]),
            submitted_at=datetime.now()
        )
        db_session.add(candidate)
        db_session.commit()
        candidate_id = candidate.id
        print(f"New candidate record inserted with ID: {candidate_id}")
        return candidate_id
    except Exception as e:
        print(f"Database error during candidate insertion: {e}")
        traceback.print_exc()
        db_session.rollback()
        return False
    finally:
        db_session.close()

def get_taken_sets_for_email(email):
    """Get all sets taken by all candidate records for this email"""
    print(f"Getting taken sets for email: {email}")
    all_candidate_ids = get_all_candidate_ids_by_email(email)
    if not all_candidate_ids:
        print(f"No candidates found for email: {email}")
        return []
    
    try:
        db_session = Session()
        taken_sets = db_session.query(Question.set_number).distinct().\
            join(TestHistory, TestHistory.question_id == Question.question_id).\
            filter(TestHistory.candidate_id.in_(all_candidate_ids)).\
            union(
                db_session.query(Question.set_number).distinct().\
                join(Answer, Answer.question_id == Question.question_id).\
                filter(Answer.candidate_id.in_(all_candidate_ids))
            ).order_by(Question.set_number).all()
        taken_sets = [row.set_number for row in taken_sets]
        print(f"Email {email} (all candidate IDs: {all_candidate_ids}) has taken sets: {taken_sets}")
        return taken_sets
    except Exception as e:
        print(f"Error fetching taken sets for email: {e}")
        traceback.print_exc()
        return []
    finally:
        db_session.close()

def get_taken_sets(candidate_id):
    """Get sets already taken by a specific candidate"""
    print(f"Getting taken sets for candidate: {candidate_id}")
    try:
        db_session = Session()
        taken_sets = db_session.query(Question.set_number).distinct().\
            join(TestHistory, TestHistory.question_id == Question.question_id).\
            filter(TestHistory.candidate_id == candidate_id).\
            union(
                db_session.query(Question.set_number).distinct().\
                join(Answer, Answer.question_id == Question.question_id).\
                filter(Answer.candidate_id == candidate_id)
            ).order_by(Question.set_number).all()
        taken_sets = [row.set_number for row in taken_sets]
        print(f"Candidate {candidate_id} has taken sets: {taken_sets}")
        return taken_sets
    except Exception as e:
        print(f"Error fetching taken sets: {e}")
        traceback.print_exc()
        return []
    finally:
        db_session.close()

def get_next_ordered_set(taken_sets):
    """Get next available set number"""
    for set_num in range(1, 6):
        if set_num not in taken_sets:
            return set_num
    return None

def get_questions(set_number):
    """Get questions for a specific set"""
    try:
        db_session = Session()
        questions = db_session.query(Question).filter(Question.set_number == set_number).\
            order_by(Question.question_id).all()
        result = [{
            'question_id': q.question_id,
            'question_text': q.question_text,
            'option_a': q.option_a,
            'option_b': q.option_b,
            'option_c': q.option_c,
            'option_d': q.option_d,
            'correct_option': q.correct_option
        } for q in questions]
        print(f"Fetched {len(result)} questions for set {set_number}")
        return result
    except Exception as e:
        print(f"Error fetching questions for set {set_number}: {e}")
        traceback.print_exc()
        return []
    finally:
        db_session.close()

def assign_questions_to_history(candidate_id, set_number, questions):
    """Assign questions to test history for tracking"""
    try:
        db_session = Session()
        # Check if questions are already assigned
        existing_count = db_session.query(TestHistory).\
            join(Question, TestHistory.question_id == Question.question_id).\
            filter(TestHistory.candidate_id == candidate_id, Question.set_number == set_number).count()
        
        if existing_count > 0:
            print(f"Set {set_number} already assigned to candidate {candidate_id} ({existing_count} questions)")
            return True
        
        # Get next attempt number
        max_attempt = db_session.query(func.coalesce(func.max(TestHistory.attempt_number), 0)).\
            filter(TestHistory.candidate_id == candidate_id).scalar() or 0
        attempt_number = max_attempt + 1
        
        current_time = datetime.now()
        for question in questions:
            test_history = TestHistory(
                candidate_id=candidate_id,
                question_id=question['question_id'],
                attempt_number=attempt_number,
                assigned_at=current_time
            )
            db_session.add(test_history)
        
        db_session.commit()
        print(f"Assigned {len(questions)} questions to history for candidate {candidate_id}, set {set_number}, attempt {attempt_number}")
        return True
    except Exception as e:
        print(f"Error assigning questions to history: {e}")
        traceback.print_exc()
        db_session.rollback()
        return False
    finally:
        db_session.close()

def save_test_results(candidate_id, set_number, questions, answers):
    """Save test results to database"""
    try:
        db_session = Session()
        # Check for existing answers
        existing_answers = db_session.query(Answer).\
            join(Question, Answer.question_id == Question.question_id).\
            filter(Answer.candidate_id == candidate_id, Question.set_number == set_number).count()
        
        if existing_answers > 0:
            print(f"Answers already exist for candidate {candidate_id}, set {set_number}. Updating...")
            db_session.query(Answer).\
                join(Question, Answer.question_id == Question.question_id).\
                filter(Answer.candidate_id == candidate_id, Question.set_number == set_number).delete()
            db_session.query(Score).\
                filter(Score.candidate_id == candidate_id, Score.total_questions == db_session.query(func.count()).\
                       select_from(Question).filter(Question.set_number == set_number).scalar()).delete()
        
        correct_answers = 0
        total_questions = len(questions)
        answered_questions = len([a for a in answers.values() if a and a.strip()])
        
        print(f"Processing {total_questions} questions for candidate {candidate_id}, set {set_number}")
        print(f"Candidate answered {answered_questions} questions")
        
        current_time = datetime.now()
        
        # Get next attempt number for scores
        max_attempt = db_session.query(func.coalesce(func.max(Score.attempt_number), 0)).\
            filter(Score.candidate_id == candidate_id).scalar() or 0
        attempt_number = max_attempt + 1
        
        # Create score entry
        score = Score(
            candidate_id=candidate_id,
            attempt_number=attempt_number,
            total_questions=total_questions,
            correct_answers=0,  # Will update after processing answers
            score_percent=0.0,  # Will update after processing answers
            submitted_at=current_time
        )
        db_session.add(score)
        db_session.flush()  # Get score_id before committing
        
        for question in questions:
            question_id = question["question_id"]
            user_answer = answers.get(str(question_id), "").strip()
            
            is_correct = 0
            if user_answer and user_answer == question["correct_option"]:
                is_correct = 1
                correct_answers += 1
            
            answer = Answer(
                candidate_id=candidate_id,
                question_id=question_id,
                selected_option=user_answer or None,
                is_correct=is_correct,
                answered_at=current_time,
                score_id=score.score_id
            )
            db_session.add(answer)
        
        score_percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        score.correct_answers = correct_answers
        score.score_percent = score_percentage
        
        print(f"Results: {correct_answers} correct out of {answered_questions} answered, {total_questions} total")
        print(f"Score percentage: {score_percentage:.1f}%")
        
        db_session.commit()
        print(f"Successfully saved results for candidate {candidate_id}, set {set_number}")
        return True
    except Exception as e:
        print(f"Error saving test results: {e}")
        traceback.print_exc()
        db_session.rollback()
        return False
    finally:
        db_session.close()

# ---------- ROUTES ----------
@app.route('/', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            form = request.form
            tech_stack = request.form.getlist('tech_stack')
            has_exp = form.get('has_experience') == 'Yes'

            print(f"Registration form data: {dict(form)}")
            print(f"Tech stack: {tech_stack}")

            required_fields = ['full_name', 'email', 'phone', 'area', 'city', 'pincode', 'position']
            missing = [k for k in required_fields if not form.get(k, '').strip()]
            
            if not tech_stack:
                missing.append("Tech Stack")

            if missing:
                flash(f"Please fill all required fields: {', '.join(missing)}", "danger")
                return render_template('register.html', form=form)

            if has_exp:
                exp_fields = ['previous_company', 'role', 'domain', 'years_experience']
                missing_exp = [k for k in exp_fields if not form.get(k, '').strip()]
                
                if missing_exp:
                    flash(f"Please fill all experience fields: {', '.join(missing_exp)}", "danger")
                    return render_template('register.html', form=form)
                
                try:
                    years_exp = float(form.get('years_experience', 0))
                    if years_exp <= 0:
                        flash("Years of experience must be greater than 0.", "danger")
                        return render_template('register.html', form=form)
                except ValueError:
                    flash("Please enter a valid number for years of experience.", "danger")
                    return render_template('register.html', form=form)

            email = form.get('email', '').strip().lower()
            if not validate_email(email):
                flash("Invalid email format.", "danger")
                return render_template('register.html', form=form)

            if not validate_phone(form.get('phone', '').strip()):
                flash("Phone must be exactly 10 digits.", "danger")
                return render_template('register.html', form=form)

            if not validate_pincode(form.get('pincode', '').strip()):
                flash("Pincode must be exactly 6 digits.", "danger")
                return render_template('register.html', form=form)

            current_attempt_count = get_attempt_number_for_email(email)
            next_attempt_number = current_attempt_count + 1
            
            if current_attempt_count >= 5:
                flash("You have already completed all available test sets (maximum 5 attempts).", "info")
                return render_template('register.html', form=form)

            candidate_data = {
                "full_name": form['full_name'].strip(),
                "email": email,
                "phone": form['phone'].strip(),
                "address": {
                    "area": form['area'].strip(), 
                    "city": form['city'].strip(), 
                    "pincode": form['pincode'].strip()
                },
                "position": form['position'].strip(),
                "tech_stack": tech_stack,
                "experience": {
                    "has_experience": has_exp,
                    "previous_company": form.get('previous_company', '').strip(),
                    "role": form.get('role', '').strip(),
                    "domain": form.get('domain', '').strip(),
                    "years_experience": float(form.get('years_experience') or 0)
                }
            }

            print(f"Creating NEW candidate record (attempt #{next_attempt_number}): {candidate_data}")
            candidate_id = insert_candidate(candidate_data)
            
            if candidate_id:
                session.clear()
                session["candidate_id"] = candidate_id
                session["candidate_email"] = email
                session["attempt_number"] = next_attempt_number
                
                if next_attempt_number > 1:
                    flash(f"Welcome to the assessment! ", "info")
                else:
                    flash("Registration successful! Your assessment is ready.", "success")
                
                return redirect(url_for("test"))
            else:
                flash("Error during registration. Please try again.", "danger")
                return render_template('register.html', form=form)

        except Exception as e:
            print(f"Error in registration: {e}")
            traceback.print_exc()
            flash("An unexpected error occurred. Please try again.", "danger")
            return render_template('register.html', form=request.form)

    return render_template('register.html', form={})

@app.route('/test', methods=['GET', 'POST'])
def test():
    if 'candidate_id' not in session:
        flash("Please register first to take the test.", "warning")
        return redirect(url_for("register"))
    
    candidate_id = session['candidate_id']
    candidate_email = session.get('candidate_email', '')
    attempt_number = session.get('attempt_number', 1)
    print(f"Test page accessed by candidate ID: {candidate_id}, Email: {candidate_email}, Attempt: {attempt_number}")

    if request.method == 'POST':
        try:
            current_set = int(request.form.get('current_set', 0))
            if current_set == 0:
                flash("Invalid test submission.", "danger")
                return redirect(url_for("test"))
            
            print(f"Processing test submission for candidate {candidate_id}, set {current_set}")
            
            answers = {}
            for key, value in request.form.items():
                if key.startswith('q_') and value and value.strip():
                    try:
                        question_id = int(key[2:])
                        answers[question_id] = value.strip()
                    except ValueError:
                        print(f"Invalid question ID in form: {key}")
                        continue
            
            print(f"Candidate {candidate_id} submitted answers for set {current_set}: {len(answers)} questions answered")
            
            questions = get_questions(current_set)
            if not questions:
                flash("Error retrieving questions. Please try again.", "danger")
                return redirect(url_for("test"))
            
            if save_test_results(candidate_id, current_set, questions, answers):
                flash("Assessment submitted successfully!", "success")
                session['last_completed_set'] = current_set
                session['test_completed'] = True  # Mark test as completed
                print(f"Test results saved for candidate {candidate_id}, set {current_set}")
            else:
                flash("Failed to save assessment results. Please contact support.", "danger")
            
            return redirect(url_for("completed"))
            
        except Exception as e:
            print(f"Error processing test submission: {e}")
            traceback.print_exc()
            flash("An error occurred while submitting your test. Please try again.", "danger")
            return redirect(url_for("test"))

    try:
        assigned_set = attempt_number
        
        if assigned_set > 5:
            flash("No more assessments available. Maximum 5 attempts allowed.", "info")
            return redirect(url_for("completed"))
        
        taken_sets_for_candidate = get_taken_sets(candidate_id)
        if assigned_set in taken_sets_for_candidate:
            flash(f"You have already completed set {assigned_set} in this session.", "info")
            session['last_completed_set'] = assigned_set
            session['test_completed'] = True
            return redirect(url_for("completed"))

        print(f"Assigning set {assigned_set} to candidate {candidate_id} (attempt #{attempt_number})")

        questions = get_questions(assigned_set)
        if not questions:
            flash(f"No questions available for set {assigned_set}. Please contact support.", "danger")
            return redirect(url_for("register"))
        
        if not assign_questions_to_history(candidate_id, assigned_set, questions):
            print("Failed to assign questions to history, but continuing...")
        
        print(f"Displaying {len(questions)} questions for set {assigned_set} (attempt #{attempt_number})")
        return render_template('test.html', 
                             questions=questions, 
                             current_set=assigned_set, 
                             attempt_number=attempt_number,
                             test_duration=TEST_DURATION_MINUTES,
                             candidate_id=candidate_id)  # Pass candidate_id to template
        
    except Exception as e:
        print(f"Error displaying test: {e}")
        traceback.print_exc()
        flash("An error occurred while loading the test. Please try again.", "danger")
        return redirect(url_for("register"))

@app.route('/upload-video', methods=['POST'])
def upload_video():
    if 'candidate_id' not in session:
        return jsonify({'message': 'Unauthorized access'}), 401
    
    candidate_id = session['candidate_id']
    attempt_number = session.get('attempt_number', 1)
    
    if 'video' not in request.files:
        print(f"No video file received for candidate {candidate_id}")
        return jsonify({'message': 'No video file'}), 400
    
    video = request.files['video']
    if video:
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            filename = f"candidate{candidate_id}attempt{attempt_number}{timestamp}.webm"
            s3_key = f"Interview-questions/interview-videos/{filename}"  # Store under Interview-questions/interview-videos/
            
            # Upload to S3
            s3_client.upload_fileobj(
                video,
                S3_BUCKET,
                s3_key,
                ExtraArgs={'ContentType': 'video/webm'}  # Set content type for video
            )
            print(f"Video uploaded to S3 for candidate {candidate_id}: {s3_key}")
            return jsonify({'message': 'Video uploaded to S3'}), 200
        except ClientError as e:
            print(f"Error uploading video to S3 for candidate {candidate_id}: {e}")
            return jsonify({'message': f'Error uploading video: {str(e)}'}), 500
        except Exception as e:
            print(f"Unexpected error uploading video for candidate {candidate_id}: {e}")
            return jsonify({'message': f'Error uploading video: {str(e)}'}), 500
    
    return jsonify({'message': 'Error uploading video'}), 400

@app.route('/completed')
def completed():
    if 'candidate_id' not in session:
        flash("Please register first.", "warning")
        return redirect(url_for("register"))
    
    candidate_id = session['candidate_id']
    candidate_email = session.get('candidate_email', '')
    current_set = session.get('last_completed_set', session.get('attempt_number', 1))
    attempt_number = session.get('attempt_number', 1)
    
    total_answered = 0
    total_questions = 30
    
    try:
        db_session = Session()
        total_answered = db_session.query(Answer).\
            join(Question, Answer.question_id == Question.question_id).\
            filter(Answer.candidate_id == candidate_id, Question.set_number == current_set,
                   Answer.selected_option != None, Answer.selected_option != '').count()
        
        total_questions = db_session.query(Question).filter(Question.set_number == current_set).count() or 30
        
        print(f"Candidate {candidate_id} (attempt #{attempt_number}) answered {total_answered} out of {total_questions} questions in set {current_set}")
        
    except Exception as e:
        print(f"Error getting completion stats: {e}")
        traceback.print_exc()
    finally:
        db_session.close()
    
    # Clear session to prevent back-button access
    session.clear()
    return render_template("completed.html", 
                         total_answered=total_answered, 
                         total_questions=total_questions,
                         current_set=current_set,
                         attempt_number=attempt_number,
                         success=True)

@app.route('/debug/db')
def debug_db():
    try:
        db_session = Session()
        result = db_session.query(func.literal(1)).scalar()
        db_session.close()
        return f"Database connection successful! Test query result: {result}"
    except Exception as e:
        return f"Database error: {e}"

@app.route('/debug/tables')
def debug_tables():
    try:
        db_session = Session()
        tables_info = {}
        
        for table in ['candidates', 'questions', 'test_history', 'answers', 'scores']:
            try:
                # Use SQLAlchemy's reflection to get table structure
                table_obj = Table(table, Base.metadata, autoload_with=engine)
                tables_info[table] = [(column.name, str(column.type)) for column in table_obj.columns]
            except Exception as e:
                tables_info[table] = f"Error: {e}"
        
        db_session.close()
        
        result = "<h2>Database Tables Structure:</h2>"
        for table, info in tables_info.items():
            result += f"<h3>{table}</h3><pre>{info}</pre>"
        
        return result
    except Exception as e:
        return f"Database error: {e}"

@app.route('/debug/candidate-history/<email>')
def debug_candidate_history(email):
    try:
        db_session = Session()
        candidates = db_session.query(Candidate).filter(func.lower(Candidate.email) == func.lower(email)).\
            order_by(Candidate.submitted_at).all()
        
        result = f"<h2>All Records for Email: {email}</h2>"
        result += f"<h3>Candidates ({len(candidates)} records):</h3><pre>{[(c.id, c.full_name, c.email, c.submitted_at) for c in candidates]}</pre>"
        
        if candidates:
            candidate_ids = [c.id for c in candidates]
            
            test_history = db_session.query(TestHistory).filter(TestHistory.candidate_id.in_(candidate_ids)).\
                order_by(TestHistory.assigned_at).all()
            result += f"<h3>Test History ({len(test_history)} records):</h3><pre>{[(th.candidate_id, th.question_id, th.attempt_number, th.assigned_at) for th in test_history]}</pre>"
            
            answers = db_session.query(Answer).filter(Answer.candidate_id.in_(candidate_ids)).\
                order_by(Answer.answered_at).all()
            result += f"<h3>Answers ({len(answers)} records):</h3><pre>{[(a.candidate_id, a.question_id, a.selected_option, a.is_correct, a.answered_at) for a in answers]}</pre>"
            
            scores = db_session.query(Score).filter(Score.candidate_id.in_(candidate_ids)).\
                order_by(Score.submitted_at).all()
            result += f"<h3>Scores ({len(scores)} records):</h3><pre>{[(s.candidate_id, s.score_id, s.attempt_number, s.total_questions, s.correct_answers, s.score_percent, s.submitted_at) for s in scores]}</pre>"
        
        db_session.close()
        return result
    except Exception as e:
        return f"Database error: {e}"

if __name__ == '__main__':
    print("Starting Flask Assessment Application...")
    app.run(debug=True, host='0.0.0.0', port=8080)