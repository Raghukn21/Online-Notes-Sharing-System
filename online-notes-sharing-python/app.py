import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from database import users_collection, uploads_collection
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'doc', 'docx', 'ppt', 'zip'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.name = user_data['name']
        self.email = user_data['email']
        self.role = user_data['role']
        self.course = user_data['course']

@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({"_id": ObjectId(user_id)})
    if user_data:
        return User(user_data)
    return None

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        repassword = request.form['repassword']
        role = request.form['role']
        course = request.form['course']
        gender = request.form['gender']

        if password != repassword:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('signup'))

        if users_collection.find_one({"username": username}):
            flash('Username is already taken', 'danger')
            return redirect(url_for('signup'))

        if users_collection.find_one({"email": email}):
            flash('Email is already taken', 'danger')
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)
        user_data = {
            "username": username,
            "name": name,
            "email": email,
            "password": hashed_password,
            "role": role,
            "course": course,
            "gender": gender,
            "joindate": datetime.now().strftime("%B %d, %Y"),
            "image": "profile.jpg",
            "about": "N/A"
        }
        users_collection.insert_one(user_data)
        flash('Successfully registered! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['user']
        password = request.form['pass']
        
        user_data = users_collection.find_one({"username": username})
        if user_data and check_password_hash(user_data['password'], password):
            user = User(user_data)
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/biometric_login')
def biometric_login():
    """Simulated biometric login endpoint"""
    username = request.args.get('username', '').strip()
    bio_type = request.args.get('type', 'fingerprint')
    
    if not username:
        flash('Please enter your username before using biometric login.', 'danger')
        return redirect(url_for('login'))
        
    user_data = users_collection.find_one({"username": username})
    if not user_data:
        flash(f'No account found for username "{username}". Check spelling and try again.', 'danger')
        return redirect(url_for('login'))
        
    user = User(user_data)
    login_user(user)
    flash(f'{bio_type.title()} authentication successful!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # If admin, show all files, otherwise show approved files + user's own files
    if current_user.role == 'admin':
        uploads = list(uploads_collection.find())
    else:
        # Notes for user's course that are approved
        uploads = list(uploads_collection.find({
            "$or": [
                {"file_uploaded_to": current_user.course, "status": "approved"},
                {"file_uploader": current_user.username}
            ]
        }))
    return render_template('dashboard.html', uploads=uploads)

@app.route('/approve/<file_id>')
@login_required
def approve_note(file_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    
    uploads_collection.update_one({"_id": ObjectId(file_id)}, {"$set": {"status": "approved"}})
    flash('Note approved successfully', 'success')
    return redirect(url_for('dashboard'))

@app.route('/delete/<file_id>')
@login_required
def delete_note(file_id):
    # Admin can delete any note, users can delete their own
    note = uploads_collection.find_one({"_id": ObjectId(file_id)})
    if not note:
        flash('Note not found', 'danger')
        return redirect(url_for('dashboard'))
    
    if current_user.role == 'admin' or note['file_uploader'] == current_user.username:
        # Delete file from filesystem
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], note['file'])
        if os.path.exists(file_path):
            os.remove(file_path)
            
        uploads_collection.delete_one({"_id": ObjectId(file_id)})
        flash('Note deleted successfully', 'success')
    else:
        flash('Permission denied', 'danger')
        
    return redirect(url_for('dashboard'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_note():
    if current_user.role == 'admin':
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add random prefix like PHP did
            import random
            random_prefix = random.randint(1000, 1000000)
            file_ext = filename.rsplit('.', 1)[1].lower()
            new_filename = f"{random_prefix}.{file_ext}"
            
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
            
            upload_data = {
                "file_name": title,
                "file_description": description,
                "file_type": file_ext,
                "file_uploader": current_user.username,
                "file_uploaded_on": datetime.now(),
                "file_uploaded_to": current_user.course,
                "file": new_filename,
                "status": "not approved yet"
            }
            uploads_collection.insert_one(upload_data)
            flash('File uploaded successfully. It will be published after admin approves it.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid file type', 'danger')
            return redirect(request.url)

    return render_template('uploadnote.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
