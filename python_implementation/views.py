import os
import uuid
import hashlib
import json
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.core.mail import send_mail
from mongoengine import Q as MongoQ

from .models import User, FileUpload, UserActivity, BiometricData, SystemSettings
from .forms import UserRegistrationForm, UserLoginForm, FileUploadForm
from .decorators import role_required
from .utils import (
    generate_file_hash, validate_file_type, get_file_size_mb,
    log_user_activity, send_notification_email, 
    process_face_recognition, process_fingerprint_auth
)
from .serializers import FileUploadSerializer, UserActivitySerializer

# Authentication Views
def index(request):
    """Home page view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'notes/index.html')

def signup_view(request):
    """User registration view"""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.is_verified = False
            user.save()
            
            # Create user profile
            UserProfile.objects.create(user=user)
            
            # Log activity
            log_user_activity(
                user_id=user.id,
                username=user.username,
                user_role=user.role,
                activity_type='signup',
                description=f'New user registered: {user.username}',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
            
            # Send verification email
            send_verification_email(user)
            
            messages.success(request, 'Registration successful! Please check your email for verification.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'notes/signup.html', {'form': form})

def login_view(request):
    """User login view"""
    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            
            user = authenticate(request, username=username, password=password)
            if user is not None:
                if user.is_active:
                    login(request, user)
                    
                    # Log activity
                    log_user_activity(
                        user_id=user.id,
                        username=user.username,
                        user_role=user.role,
                        activity_type='login',
                        description=f'User logged in: {user.username}',
                        ip_address=request.META.get('REMOTE_ADDR'),
                        user_agent=request.META.get('HTTP_USER_AGENT')
                    )
                    
                    messages.success(request, f'Welcome back, {user.username}!')
                    return redirect('dashboard')
                else:
                    messages.error(request, 'Your account is disabled.')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = UserLoginForm()
    
    return render(request, 'notes/login.html', {'form': form})

@login_required
def logout_view(request):
    """User logout view"""
    username = request.user.username
    logout(request)
    
    # Log activity
    log_user_activity(
        user_id=request.user.id,
        username=username,
        user_role=request.user.role,
        activity_type='logout',
        description=f'User logged out: {username}',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT')
    )
    
    messages.info(request, 'You have been logged out successfully.')
    return redirect('login')

# Dashboard Views
@login_required
def dashboard_view(request):
    """Main dashboard view"""
    user = request.user
    
    # Get user's files
    user_files = FileUpload.objects(user_id=user.id).order_by('-uploaded_at')
    
    # Get recent activities
    recent_activities = UserActivity.objects(
        user_id=user.id
    ).order_by('-timestamp')[:10]
    
    # Get statistics
    total_files = user_files.count()
    approved_files = user_files(status='approved').count()
    pending_files = user_files(status='pending').count()
    
    # Get system notifications
    notifications = get_user_notifications(user)
    
    context = {
        'user': user,
        'files': user_files[:10],  # Show recent 10 files
        'activities': recent_activities,
        'stats': {
            'total_files': total_files,
            'approved_files': approved_files,
            'pending_files': pending_files,
            'total_downloads': sum(f.download_count for f in user_files)
        },
        'notifications': notifications
    }
    
    return render(request, 'notes/dashboard.html', context)

@login_required
@role_required(['teacher', 'admin'])
def upload_note(request):
    """File upload view"""
    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']
            
            # Validate file
            if not validate_file_type(uploaded_file.content_type):
                messages.error(request, 'Invalid file type. Please upload PDF, DOC, PPT, TXT, or ZIP files.')
                return render(request, 'notes/upload.html', {'form': form})
            
            if get_file_size_mb(uploaded_file.size) > 50:
                messages.error(request, 'File size exceeds 50MB limit.')
                return render(request, 'notes/upload.html', {'form': form})
            
            # Generate unique filename
            file_id = str(uuid.uuid4())
            file_extension = os.path.splitext(uploaded_file.name)[1]
            filename = f"{file_id}{file_extension}"
            
            # Save file
            file_path = default_storage.save(f'uploads/{filename}', uploaded_file)
            
            # Generate file hash
            file_hash = generate_file_hash(uploaded_file)
            
            # Create file record
            file_record = FileUpload(
                id=file_id,
                user_id=request.user.id,
                username=request.user.username,
                user_role=request.user.role,
                filename=filename,
                original_filename=uploaded_file.name,
                file_path=file_path,
                file_size=uploaded_file.size,
                file_type=file_extension[1:].upper() if file_extension else 'UNKNOWN',
                mime_type=uploaded_file.content_type,
                file_hash=file_hash,
                title=form.cleaned_data['title'],
                description=form.cleaned_data['description'],
                subject=form.cleaned_data['subject'],
                tags=form.cleaned_data['tags'].split(',') if form.cleaned_data['tags'] else []
            )
            file_record.save()
            
            # Log activity
            log_user_activity(
                user_id=request.user.id,
                username=request.user.username,
                user_role=request.user.role,
                activity_type='upload',
                description=f'File uploaded: {uploaded_file.name}',
                file_id=file_id,
                metadata={
                    'file_size': uploaded_file.size,
                    'file_type': uploaded_file.content_type
                },
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
            
            # Notify admins
            notify_admins_new_upload(file_record)
            
            messages.success(request, 'File uploaded successfully! It will be available after approval.')
            return redirect('dashboard')
    else:
        form = FileUploadForm()
    
    return render(request, 'notes/upload.html', {'form': form})

# Admin Views
@login_required
@role_required(['admin'])
def admin_activities(request):
    """Admin activities view"""
    # Get all files
    all_files = FileUpload.objects().order_by('-uploaded_at')
    
    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        all_files = all_files(status=status_filter)
    
    # Pagination
    paginator = Paginator(all_files, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get statistics
    stats = {
        'total_files': all_files.count(),
        'pending_files': all_files(status='pending').count(),
        'approved_files': all_files(status='approved').count(),
        'rejected_files': all_files(status='rejected').count(),
    }
    
    context = {
        'files': page_obj,
        'stats': stats,
        'status_filter': status_filter
    }
    
    return render(request, 'notes/admin_activities.html', context)

@login_required
@role_required(['admin'])
def approve_note(request, file_id):
    """Approve or reject a file"""
    if request.method == 'POST':
        action = request.POST.get('action')  # 'approve' or 'reject'
        reason = request.POST.get('reason', '')
        
        try:
            file_record = FileUpload.objects.get(id=file_id)
            
            if action == 'approve':
                file_record.status = 'approved'
                file_record.approved_by = request.user.id
                file_record.approved_at = timezone.now()
                
                # Notify file owner
                send_notification_email(
                    user_email=get_user_email(file_record.user_id),
                    subject='Your file has been approved',
                    message=f'Your file "{file_record.title}" has been approved and is now available.'
                )
                
                messages.success(request, f'File "{file_record.title}" has been approved.')
                
            elif action == 'reject':
                file_record.status = 'rejected'
                file_record.rejection_reason = reason
                
                # Notify file owner
                send_notification_email(
                    user_email=get_user_email(file_record.user_id),
                    subject='Your file has been rejected',
                    message=f'Your file "{file_record.title}" has been rejected. Reason: {reason}'
                )
                
                messages.success(request, f'File "{file_record.title}" has been rejected.')
            
            file_record.save()
            
            # Log activity
            log_user_activity(
                user_id=request.user.id,
                username=request.user.username,
                user_role=request.user.role,
                activity_type=action,
                description=f'File {action}d: {file_record.title}',
                file_id=file_id,
                metadata={'reason': reason} if action == 'reject' else {},
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
            
        except FileUpload.DoesNotExist:
            messages.error(request, 'File not found.')
        
        return redirect('admin_activities')
    
    return redirect('admin_activities')

@login_required
@role_required(['admin'])
def delete_note(request, file_id):
    """Delete a file"""
    try:
        file_record = FileUpload.objects.get(id=file_id)
        
        # Delete physical file
        if default_storage.exists(file_record.file_path):
            default_storage.delete(file_record.file_path)
        
        # Delete database record
        file_record.delete()
        
        # Log activity
        log_user_activity(
            user_id=request.user.id,
            username=request.user.username,
            user_role=request.user.role,
            activity_type='delete',
            description=f'File deleted: {file_record.title}',
            file_id=file_id,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT')
        )
        
        messages.success(request, f'File "{file_record.title}" has been deleted.')
        
    except FileUpload.DoesNotExist:
        messages.error(request, 'File not found.')
    
    return redirect('admin_activities')

# Profile View
@login_required
def profile_view(request):
    """User profile view"""
    user = request.user
    user_profile, created = UserProfile.objects.get_or_create(user=user)
    
    if request.method == 'POST':
        # Update profile information
        user.email = request.POST.get('email', user.email)
        user.phone_number = request.POST.get('phone_number', user.phone_number)
        
        if 'profile_picture' in request.FILES:
            user.profile_picture = request.FILES['profile_picture']
        
        user.save()
        
        # Update profile
        user_profile.bio = request.POST.get('bio', user_profile.bio)
        user_profile.website = request.POST.get('website', user_profile.website)
        user_profile.location = request.POST.get('location', user_profile.location)
        user_profile.save()
        
        # Log activity
        log_user_activity(
            user_id=user.id,
            username=user.username,
            user_role=user.role,
            activity_type='profile_update',
            description='Profile information updated',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT')
        )
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')
    
    # Get user's files
    user_files = FileUpload.objects(user_id=user.id).order_by('-uploaded_at')
    
    context = {
        'user': user,
        'profile': user_profile,
        'files': user_files,
        'stats': {
            'total_files': user_files.count(),
            'approved_files': user_files(status='approved').count(),
            'total_downloads': sum(f.download_count for f in user_files)
        }
    }
    
    return render(request, 'notes/profile.html', context)

# Biometric Authentication Views
@login_required
def biometric_login_check(request):
    """Check biometric login availability"""
    user_id = request.user.id
    has_face_data = BiometricData.objects(
        user_id=user_id, 
        biometric_type='face', 
        is_active=True
    ).count() > 0
    
    has_fingerprint_data = BiometricData.objects(
        user_id=user_id, 
        biometric_type='fingerprint', 
        is_active=True
    ).count() > 0
    
    return JsonResponse({
        'has_face_data': has_face_data,
        'has_fingerprint_data': has_fingerprint_data
    })

@login_required
def enroll_biometric(request):
    """Enroll biometric data"""
    if request.method == 'POST':
        biometric_type = request.POST.get('biometric_type')
        biometric_data = request.POST.get('biometric_data')
        
        if not biometric_type or not biometric_data:
            return JsonResponse({'error': 'Missing biometric data'}, status=400)
        
        # Deactivate existing biometric data of same type
        BiometricData.objects(
            user_id=request.user.id,
            biometric_type=biometric_type
        ).update(is_active=False)
        
        # Create new biometric record
        biometric_record = BiometricData(
            user_id=request.user.id,
            biometric_type=biometric_type,
            biometric_data=biometric_data.encode('utf-8')
        )
        biometric_record.save()
        
        # Log activity
        log_user_activity(
            user_id=request.user.id,
            username=request.user.username,
            user_role=request.user.role,
            activity_type='profile_update',
            description=f'Biometric data enrolled: {biometric_type}',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT')
        )
        
        return JsonResponse({'success': True, 'message': f'{biometric_type} enrolled successfully'})
    
    return render(request, 'notes/enroll_biometric.html')

# WebAuthn Views
@csrf_exempt
@login_required
def webauthn_register_begin(request):
    """Begin WebAuthn registration"""
    try:
        # WebAuthn registration logic here
        # This would integrate with a WebAuthn library
        challenge = os.urandom(32).hex()
        
        # Store challenge in session
        request.session['webauthn_challenge'] = challenge
        
        return JsonResponse({
            'challenge': challenge,
            'user': {
                'id': str(request.user.id),
                'name': request.user.username,
                'displayName': request.user.username
            }
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@login_required
def webauthn_register_complete(request):
    """Complete WebAuthn registration"""
    try:
        # WebAuthn registration completion logic here
        credential_data = json.loads(request.body)
        
        # Verify and store credential
        # This would integrate with a WebAuthn library
        
        return JsonResponse({'success': True})
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def webauthn_login_begin(request):
    """Begin WebAuthn login"""
    try:
        username = request.POST.get('username')
        
        if not username:
            return JsonResponse({'error': 'Username required'}, status=400)
        
        # Get user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
        
        # Generate challenge
        challenge = os.urandom(32).hex()
        request.session['webauthn_challenge'] = challenge
        
        return JsonResponse({
            'challenge': challenge,
            'user': {
                'id': str(user.id),
                'name': user.username,
                'displayName': user.username
            }
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def webauthn_login_complete(request):
    """Complete WebAuthn login"""
    try:
        # WebAuthn login completion logic here
        credential_data = json.loads(request.body)
        
        # Verify credential and authenticate user
        # This would integrate with a WebAuthn library
        
        return JsonResponse({'success': True})
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# Face Recognition Views
@login_required
def face_login(request):
    """Face recognition login"""
    if request.method == 'POST':
        face_data = request.POST.get('face_data')
        username = request.POST.get('username')
        
        if not face_data or not username:
            return JsonResponse({'error': 'Missing face data or username'}, status=400)
        
        try:
            # Process face recognition
            result = process_face_recognition(username, face_data)
            
            if result['success']:
                # Authenticate user
                user = User.objects.get(username=username)
                login(request, user)
                
                # Log activity
                log_user_activity(
                    user_id=user.id,
                    username=user.username,
                    user_role=user.role,
                    activity_type='login',
                    description=f'Face recognition login: {username}',
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT')
                )
                
                return JsonResponse({'success': True, 'redirect_url': '/dashboard/'})
            else:
                return JsonResponse({'error': 'Face recognition failed'}, status=401)
        
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@login_required
def face_enroll(request):
    """Enroll face data"""
    if request.method == 'POST':
        face_data = request.POST.get('face_data')
        
        if not face_data:
            return JsonResponse({'error': 'Missing face data'}, status=400)
        
        try:
            # Process and store face data
            biometric_record = BiometricData(
                user_id=request.user.id,
                biometric_type='face',
                biometric_data=face_data.encode('utf-8')
            )
            biometric_record.save()
            
            # Log activity
            log_user_activity(
                user_id=request.user.id,
                username=request.user.username,
                user_role=request.user.role,
                activity_type='profile_update',
                description='Face data enrolled',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
            
            return JsonResponse({'success': True, 'message': 'Face data enrolled successfully'})
        
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

# API Views
@require_GET
@login_required
def api_files(request):
    """API endpoint for files"""
    user = request.user
    
    # Filter files based on user role
    if user.role == 'admin':
        files = FileUpload.objects().order_by('-uploaded_at')
    else:
        files = FileUpload.objects(
            MongoQ(user_id=user.id) | MongoQ(status='approved')
        ).order_by('-uploaded_at')
    
    # Apply filters
    status_filter = request.GET.get('status')
    if status_filter:
        files = files(status=status_filter)
    
    search_query = request.GET.get('search')
    if search_query:
        files = files(
            MongoQ(title__icontains=search_query) |
            MongoQ(description__icontains=search_query) |
            MongoQ(tags__icontains=search_query)
        )
    
    # Serialize data
    serializer = FileUploadSerializer(files, many=True)
    
    return JsonResponse({
        'files': serializer.data,
        'total': files.count()
    })

@require_POST
@login_required
def api_download_file(request, file_id):
    """API endpoint for file download"""
    try:
        file_record = FileUpload.objects.get(id=file_id)
        
        # Check permissions
        if (request.user.role != 'admin' and 
            file_record.user_id != request.user.id and 
            file_record.status != 'approved'):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Update download count
        file_record.download_count += 1
        file_record.last_accessed = timezone.now()
        file_record.save()
        
        # Log activity
        log_user_activity(
            user_id=request.user.id,
            username=request.user.username,
            user_role=request.user.role,
            activity_type='download',
            description=f'File downloaded: {file_record.title}',
            file_id=file_id,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT')
        )
        
        # Serve file
        if default_storage.exists(file_record.file_path):
            file_handle = default_storage.open(file_record.file_path, 'rb')
            response = HttpResponse(file_handle.read(), content_type=file_record.mime_type)
            response['Content-Disposition'] = f'attachment; filename="{file_record.original_filename}"'
            response['Content-Length'] = file_record.file_size
            return response
        else:
            return JsonResponse({'error': 'File not found'}, status=404)
    
    except FileUpload.DoesNotExist:
        return JsonResponse({'error': 'File not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# Utility Functions
def get_user_email(user_id):
    """Get user email by ID"""
    try:
        user = User.objects.get(id=user_id)
        return user.email
    except User.DoesNotExist:
        return None

def send_verification_email(user):
    """Send verification email to user"""
    subject = 'Verify your email address'
    message = f'''
    Hello {user.username},
    
    Please verify your email address by clicking the link below:
    http://127.0.0.1:8000/verify-email/{user.id}/
    
    Thank you for registering!
    '''
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"Failed to send verification email: {e}")

def notify_admins_new_upload(file_record):
    """Notify admins about new file upload"""
    admin_users = User.objects(role='admin', is_active=True)
    
    for admin in admin_users:
        send_notification_email(
            user_email=admin.email,
            subject='New File Upload Pending Approval',
            message=f'''
            A new file has been uploaded and requires your approval:
            
            Title: {file_record.title}
            Uploaded by: {file_record.username}
            Subject: {file_record.subject}
            
            Please review and approve/reject the file.
            '''
        )

def get_user_notifications(user):
    """Get user notifications"""
    notifications = []
    
    # Get pending files count for teachers
    if user.role == 'teacher':
        pending_count = FileUpload.objects(
            user_id=user.id,
            status='pending'
        ).count()
        
        if pending_count > 0:
            notifications.append({
                'type': 'info',
                'message': f'You have {pending_count} file(s) pending approval',
                'icon': 'clock'
            })
    
    # Get system announcements
    announcements = SystemSettings.objects(key__startswith='announcement_')
    for announcement in announcements:
        notifications.append({
            'type': 'success',
            'message': announcement.value,
            'icon': 'bell'
        })
    
    return notifications
