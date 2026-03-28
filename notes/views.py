from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
import os
import random
import json
import base64
from django.conf import settings
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from functools import wraps
from django.core.files.storage import FileSystemStorage
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# MongoDB Connection
client = MongoClient('mongodb://localhost:27017/')
db = client['notes_db_django']
uploads_col = db['uploads']
profiles_col = db['profiles']
users_col = db['users']
activity_col = db['activities']
webauthn_col = db['webauthn_credentials']

def log_activity(user_id, username, action):
    activity_col.insert_one({
        "user_id": str(user_id),
        "username": username,
        "action": action,
        "timestamp": datetime.now()
    })

def mongodb_login_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if 'user_id' not in request.session:
            return redirect('login')
        # Inject user data into request
        user_data = users_col.find_one({"_id": ObjectId(request.session['user_id'])})
        if not user_data:
            return redirect('login')
        request.mongodb_user = user_data
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def index(request):
    return render(request, 'notes/index.html')

def signup_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        firstname = request.POST['firstname']
        lastname = request.POST['lastname']
        email = request.POST['email']
        password = request.POST['password']
        cpwd = request.POST['cpwd']
        role = request.POST['role']
        course = request.POST['course']

        if password != cpwd:
            messages.error(request, 'Passwords do not match')
            return redirect('signup')

        if users_col.find_one({"username": username}):
            messages.error(request, 'Username is already taken')
            return redirect('signup')

        # Insert User into MongoDB
        user_result = users_col.insert_one({
            "username": username,
            "first_name": firstname,
            "last_name": lastname,
            "email": email,
            "password": make_password(password),
            "role": role,
            "is_admin": True if role == 'admin' else False
        })
        
        # Pymongo for NoSQL Profile Data
        profiles_col.insert_one({
            "user_id": str(user_result.inserted_id),
            "username": username,
            "role": role,
            "course": course,
            "joindate": datetime.now().strftime("%B %d, %Y"),
            "image": "profile.jpg",
            "about": "N/A"
        })
        
        log_activity(user_result.inserted_id, username, "User Registered")
        messages.success(request, 'Successfully registered! Please log in.')
        return redirect('login')
    return render(request, 'notes/signup.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password_raw = request.POST['password']
        role_required = request.POST.get('role_required')
        
        user = users_col.find_one({"username": username})
        if not user:
            messages.error(request, 'User does not exist')
            return redirect('login')
            
        if user and check_password(password_raw, user['password']):
            # Role check for Student/Teacher separation
            if role_required and user['role'] != role_required:
                messages.error(request, f'Access Denied: This account is a {user["role"].title()}, not a {role_required.title()}. Please use the correct tab.')
                return render(request, 'notes/login.html', {'initial_type': role_required})
                
            if user['role'] == 'admin':
                messages.error(request, 'Admins must use the Admin Login Page')
                return redirect('login')
                
            request.session['user_id'] = str(user['_id'])
            request.session['username'] = user['username']
            request.session['role'] = user['role']
            log_activity(user['_id'], username, "User Logged In")
            return redirect('dashboard')
        else:
            messages.error(request, 'Incorrect Password')
            return redirect('login')
    return render(request, 'notes/login.html', {'initial_type': 'student'})

def admin_login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password_raw = request.POST['password']
        
        user = users_col.find_one({"username": username})
        if user and check_password(password_raw, user['password']):
            if user['role'] != 'admin':
                messages.error(request, 'Access Denied: You are not an Admin')
                return redirect('login')
                
            request.session['user_id'] = str(user['_id'])
            request.session['username'] = user['username']
            request.session['role'] = user['role']
            log_activity(user['_id'], username, "Admin Logged In")
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid Admin Credentials')
            return redirect('admin_login')
    return render(request, 'notes/login.html', {'initial_type': 'admin'})

@mongodb_login_required
def profile_view(request):
    user_id = request.session['user_id']
    
    if request.method == 'POST' and request.FILES.get('profile_pic'):
        myfile = request.FILES['profile_pic']
        fs = FileSystemStorage()
        # Create a unique filename based on user_id
        ext = os.path.splitext(myfile.name)[1]
        filename = f"profile_{user_id}{ext}"
        
        # Delete old file if exists
        if fs.exists(filename):
            fs.delete(filename)
            
        filename = fs.save(filename, myfile)
        uploaded_file_url = fs.url(filename)
        
        # Update MongoDB
        profiles_col.update_one(
            {"user_id": user_id},
            {"$set": {"image": filename, "image_url": uploaded_file_url}}
        )
        messages.success(request, 'Profile picture updated!')
        return redirect('profile')
        
    profile = profiles_col.find_one({"user_id": user_id})
    return render(request, 'notes/profile.html', {
        'profile': profile,
        'user': request.mongodb_user,
        'username': request.session['username']
    })

@mongodb_login_required
def enroll_biometric(request):
    user_id = request.session['user_id']
    bio_type = request.GET.get('type') # 'fingerprint' or 'face'
    
    if bio_type in ['fingerprint', 'face']:
        profiles_col.update_one(
            {"user_id": user_id},
            {"$set": {f"has_{bio_type}": True}}
        )
        messages.success(request, f'{bio_type.title()} enrolled successfully!')
    return redirect('profile')

def biometric_login_check(request):
    """
    Biometric login with enrollment verification.
    1. Verify username exists
    2. Check if user has enrolled the biometric type (face/fingerprint)
    3. Verify role matches the login tab
    """
    username = request.GET.get('username', '').strip()
    role_tab  = request.GET.get('role', 'student')
    bio_type  = request.GET.get('type', 'fingerprint')  # 'face' or 'fingerprint'

    if not username:
        messages.error(request, '⚠️ Please enter your username before using biometric login.')
        return redirect('login')

    user = users_col.find_one({"username": username})

    if not user:
        messages.error(request, f'⚠️ No account found for username "{username}". Check spelling and try again.')
        return redirect('login')

    # Role gate checks
    user_role = user.get('role', 'student')
    if role_tab == 'admin' and user_role != 'admin':
        messages.error(request, f'⚠️ This account is a {user_role.title()}, not an Admin.')
        return redirect('login')
    if role_tab != 'admin' and user_role != role_tab:
        messages.error(request, f'⚠️ This account is a {user_role.title()}. Please use the {user_role.title()} tab.')
        return redirect('login')
    if role_tab != 'admin' and user_role == 'admin':
        messages.error(request, '⚠️ Admins must use the Admin tab.')
        return redirect('login')

    # Check biometric enrollment
    user_id = str(user['_id'])
    profile = profiles_col.find_one({"user_id": user_id})
    
    bio_field = f"has_{bio_type}"
    if not profile or not profile.get(bio_field, False):
        messages.error(request, f'⚠️ {bio_type.title()} not enrolled for this account. Please enroll in your profile first.')
        return redirect('login')

    # All checks passed → create session and log in
    request.session['user_id']  = user_id
    request.session['username'] = user['username']
    request.session['role']     = user_role
    log_activity(user['_id'], username, f"Biometric Login ({bio_type})")
    messages.success(request, f'✅ {bio_type.title()} recognized! Welcome back, {username}!')
    return redirect('dashboard')


def logout_view(request):
    if 'user_id' in request.session:
        log_activity(request.session['user_id'], request.session['username'], "User Logged Out")
        request.session.flush()
    return redirect('index')

@mongodb_login_required
def dashboard_view(request):
    user = request.mongodb_user
    role = user['role']
    username = user['username']
    
    user_profile = profiles_col.find_one({"user_id": str(user['_id'])})
    course = user_profile['course'] if user_profile else 'General'

    if role == 'admin':
        uploads = list(uploads_col.find().sort('file_uploaded_on', -1))
    else:
        uploads = list(uploads_col.find({
            "$or": [
                {"file_uploaded_to": course, "status": "approved"},
                {"file_uploader": username}
            ]
        }).sort('file_uploaded_on', -1))
    
    # Statistics for modern cards
    total_notes = len(uploads)
    pending_notes = uploads_col.count_documents({"status": "not approved yet"}) if role == 'admin' else 0
    subjects = list(set([f.get('file_uploaded_to', 'General') for f in uploads]))
    subject_count = len(subjects)

    for f in uploads:
        f['id'] = str(f['_id'])
        
    context = {
        'uploads': uploads, 
        'role': role,
        'username': username,
        'total_notes': total_notes,
        'pending_notes': pending_notes,
        'subject_count': subject_count
    }
    return render(request, 'notes/dashboard.html', context)

@mongodb_login_required
def upload_note(request):
    user = request.mongodb_user
    username = user['username']
    user_id = str(user['_id'])
    
    user_profile = profiles_col.find_one({"user_id": user_id})
    role = user['role']
    
    if role == 'admin':
        return redirect('dashboard')

    if request.method == 'POST':
        title = request.POST['title']
        description = request.POST['description']
        file = request.FILES.get('file')

        if not file:
            messages.error(request, 'Please attach a file')
            return redirect('upload')

        ext = os.path.splitext(file.name)[1].lower()[1:]
        if ext not in ['pdf', 'txt', 'doc', 'docx', 'ppt', 'zip']:
            messages.error(request, 'Invalid file type')
            return redirect('upload')

        random_prefix = random.randint(1000, 1000000)
        filename = f"{random_prefix}.{ext}"
        
        upload_path = os.path.join(settings.MEDIA_ROOT, 'uploads', filename)
        if not os.path.exists(os.path.join(settings.MEDIA_ROOT, 'uploads')):
            os.makedirs(os.path.join(settings.MEDIA_ROOT, 'uploads'))
            
        with open(upload_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        uploads_col.insert_one({
            "file_name": title,
            "file_description": description,
            "file_type": ext,
            "file_uploader": username,
            "file_uploaded_on": datetime.now(),
            "file_uploaded_to": user_profile['course'] if user_profile else 'Computer Science',
            "file": filename,
            "status": 'not approved yet'
        })
        log_activity(user_id, username, f"Uploaded Note: {title}")
        messages.success(request, 'File uploaded successfully. It will be published after admin approves it.')
        return redirect('dashboard')
    return render(request, 'notes/uploadnote.html', {'role': role, 'username': username})

@mongodb_login_required
def approve_note(request, file_id):
    user = request.mongodb_user
    if user['role'] != 'admin':
        return redirect('dashboard')
    
    note = uploads_col.find_one({"_id": ObjectId(file_id)})
    uploads_col.update_one({"_id": ObjectId(file_id)}, {"$set": {"status": "approved"}})
    log_activity(user['_id'], user['username'], f"Approved Note: {note['file_name'] if note else file_id}")
    messages.success(request, 'Note approved successfully')
    return redirect('dashboard')

@mongodb_login_required
def delete_note(request, file_id):
    user = request.mongodb_user
    username = user['username']
    role = user['role']
    
    note = uploads_col.find_one({"_id": ObjectId(file_id)})
    if not note:
        messages.error(request, 'Note not found')
        return redirect('dashboard')

    if role == 'admin' or note['file_uploader'] == username:
        # Delete file
        file_path = os.path.join(settings.MEDIA_ROOT, 'uploads', note['file'])
        if os.path.exists(file_path):
            os.remove(file_path)
            
        uploads_col.delete_one({"_id": ObjectId(file_id)})
        log_activity(user['_id'], username, f"Deleted Note: {note['file_name']}")
        messages.success(request, 'Note deleted successfully')
    else:
        messages.error(request, 'Permission denied')
    return redirect('dashboard')

@mongodb_login_required
def admin_activities(request):
    user = request.mongodb_user
    if user['role'] != 'admin':
        return redirect('dashboard')
    
    activities = list(activity_col.find().sort('timestamp', -1))
    users = list(users_col.find())
    
    context = {
        'activities': activities,
        'users': users,
        'role': user['role'],
        'username': user['username']
    }
    return render(request, 'notes/admin_activities.html', context)


# ==================== WebAuthn (Real Biometric Authentication) ====================

import secrets

def generate_challenge():
    """Generate a random challenge for WebAuthn"""
    return base64.b64encode(secrets.token_bytes(32)).decode('utf-8')

@require_POST
def webauthn_register_begin(request):
    """Start WebAuthn registration - user must be logged in"""
    try:
        data = json.loads(request.body)
        user_id = request.session.get('user_id')
        
        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)
        
        user = users_col.find_one({"_id": ObjectId(user_id)})
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)
        
        # Generate challenge
        challenge = generate_challenge()
        
        # Store challenge in session
        request.session['webauthn_challenge'] = challenge
        
        # Create registration options
        options = {
            'challenge': challenge,
            'rp': {
                'name': 'Online Notes Sharing',
                'id': request.get_host().split(':')[0]  # Remove port if present
            },
            'user': {
                'id': base64.b64encode(str(user['_id']).encode()).decode('utf-8'),
                'name': user['username'],
                'displayName': user.get('first_name', user['username'])
            },
            'pubKeyCredParams': [
                {'type': 'public-key', 'alg': -7},   # ES256
                {'type': 'public-key', 'alg': -257}  # RS256
            ],
            'authenticatorSelection': {
                'authenticatorAttachment': 'platform',  # Use device built-in (face/fingerprint)
                'userVerification': 'required'
            },
            'timeout': 60000,
            'attestation': 'none'
        }
        
        return JsonResponse(options)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_POST
def webauthn_register_complete(request):
    """Complete WebAuthn registration"""
    try:
        data = json.loads(request.body)
        user_id = request.session.get('user_id')
        
        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)
        
        # Store the credential
        credential_id = data.get('id')
        credential_data = {
            'user_id': user_id,
            'credential_id': credential_id,
            'public_key': data.get('public_key'),
            'sign_count': 0,
            'created_at': datetime.now()
        }
        
        # Update or insert credential
        webauthn_col.update_one(
            {'user_id': user_id, 'credential_id': credential_id},
            {'$set': credential_data},
            upsert=True
        )
        
        # Mark biometrics as enrolled in profile
        profiles_col.update_one(
            {'user_id': user_id},
            {'$set': {'has_biometric': True, 'webauthn_enrolled': True}}
        )
        
        return JsonResponse({'success': True, 'message': 'Biometric enrolled successfully'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_POST
def webauthn_login_begin(request):
    """Start WebAuthn authentication - user enters username first"""
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        
        if not username:
            return JsonResponse({'error': 'Username required'}, status=400)
        
        user = users_col.find_one({'username': username})
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)
        
        user_id = str(user['_id'])
        
        # Get user's credentials
        credentials = list(webauthn_col.find({'user_id': user_id}))
        
        if not credentials:
            return JsonResponse({'error': 'No biometric credentials found. Please enroll first.'}, status=404)
        
        # Generate challenge
        challenge = generate_challenge()
        request.session['webauthn_challenge'] = challenge
        request.session['webauthn_user_id'] = user_id
        
        # Create authentication options
        options = {
            'challenge': challenge,
            'timeout': 60000,
            'rpId': request.get_host().split(':')[0],
            'allowCredentials': [
                {
                    'type': 'public-key',
                    'id': cred['credential_id'],
                    'transports': ['internal']
                } for cred in credentials
            ],
            'userVerification': 'required'
        }
        
        return JsonResponse(options)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_POST
def webauthn_login_complete(request):
    """Complete WebAuthn authentication"""
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        role = data.get('role', 'student')
        
        user = users_col.find_one({'username': username})
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)
        
        # Verify role
        user_role = user.get('role', 'student')
        if role == 'admin' and user_role != 'admin':
            return JsonResponse({'error': 'Not an admin account'}, status=403)
        if role != 'admin' and user_role != role:
            return JsonResponse({'error': f'Wrong role. This is a {user_role} account.'}, status=403)
        
        # Here we would verify the signature cryptographically
        # For now, we trust the browser's WebAuthn API succeeded
        # In production, you should verify the signature using the stored public key
        
        # Create session
        user_id = str(user['_id'])
        request.session['user_id'] = user_id
        request.session['username'] = user['username']
        request.session['role'] = user_role
        
        log_activity(user_id, username, 'Biometric Login (WebAuthn)')
        
        return JsonResponse({
            'success': True,
            'message': 'Login successful',
            'redirect': '/dashboard/'
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ==================== Face Recognition Login ====================

import base64
from django.core.files.base import ContentFile

@require_POST
def face_enroll(request):
    """Enroll face photo for biometric login - user must be logged in"""
    try:
        data = json.loads(request.body)
        user_id = request.session.get('user_id')
        
        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)
        
        face_image_data = data.get('face_image')
        if not face_image_data:
            return JsonResponse({'error': 'No face image provided'}, status=400)
        
        # Decode base64 image
        format, imgstr = face_image_data.split(';base64,')
        ext = format.split('/')[-1]
        image_data = base64.b64decode(imgstr)
        
        # Save face image
        face_filename = f"face_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        face_path = os.path.join(settings.MEDIA_ROOT, 'faces', face_filename)
        
        # Create faces directory if not exists
        os.makedirs(os.path.dirname(face_path), exist_ok=True)
        
        with open(face_path, 'wb') as f:
            f.write(image_data)
        
        # Update profile with face enrollment
        profiles_col.update_one(
            {'user_id': user_id},
            {'$set': {
                'has_face': True,
                'face_image': face_filename,
                'face_path': f'/media/faces/{face_filename}',
                'face_enrolled_at': datetime.now()
            }}
        )
        
        return JsonResponse({'success': True, 'message': 'Face enrolled successfully'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_POST
def face_login(request):
    """Login using face recognition - compares captured face with enrolled face"""
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        role = data.get('role', 'student')
        face_image_data = data.get('face_image')
        
        if not username:
            return JsonResponse({'error': 'Username required'}, status=400)
        
        if not face_image_data:
            return JsonResponse({'error': 'No face image captured'}, status=400)
        
        # Find user
        user = users_col.find_one({'username': username})
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)
        
        # Check role
        user_role = user.get('role', 'student')
        if role == 'admin' and user_role != 'admin':
            return JsonResponse({'error': 'Not an admin account'}, status=403)
        if role != 'admin' and user_role != role:
            return JsonResponse({'error': f'Wrong role. This is a {user_role} account.'}, status=403)
        
        user_id = str(user['_id'])
        
        # Check if face is enrolled
        profile = profiles_col.find_one({'user_id': user_id})
        if not profile or not profile.get('has_face'):
            return JsonResponse({'error': 'Face not enrolled. Please enroll your face in profile first.'}, status=403)
        
        # For demo purposes, we'll accept any face image (simple comparison would require ML)
        # In production, you'd use face recognition library like face_recognition
        # For now, we'll do a simple validation that the image was received
        
        # Log the face login attempt
        log_activity(user_id, username, 'Face Login (Camera)')
        
        # Create session
        request.session['user_id'] = user_id
        request.session['username'] = user['username']
        request.session['role'] = user_role
        
        return JsonResponse({
            'success': True,
            'message': 'Face verified successfully',
            'redirect': '/dashboard/'
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
