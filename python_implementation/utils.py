import os
import hashlib
import uuid
import magic
import cv2
import numpy as np
from datetime import datetime, timedelta
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.utils import timezone
from mongoengine import Q as MongoQ

from .models import UserActivity, FileUpload, BiometricData

User = get_user_model()

def generate_file_hash(uploaded_file):
    """Generate SHA-256 hash of uploaded file"""
    hash_sha256 = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

def validate_file_type(content_type):
    """Validate file type against allowed types"""
    allowed_types = settings.UPLOAD_FILE_TYPES
    return content_type in allowed_types

def get_file_size_mb(file_size):
    """Convert file size from bytes to MB"""
    return file_size / (1024 * 1024)

def log_user_activity(user_id, username, user_role, activity_type, description, 
                     ip_address=None, user_agent=None, file_id=None, metadata=None):
    """Log user activity to database"""
    try:
        activity = UserActivity(
            user_id=user_id,
            username=username,
            user_role=user_role,
            activity_type=activity_type,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            file_id=file_id,
            metadata=metadata or {}
        )
        activity.save()
        
        # Cache recent activities for performance
        cache_key = f'user_activities_{user_id}'
        recent_activities = cache.get(cache_key, [])
        recent_activities.insert(0, {
            'activity_type': activity_type,
            'description': description,
            'timestamp': activity.timestamp.isoformat()
        })
        
        # Keep only last 20 activities
        recent_activities = recent_activities[:20]
        cache.set(cache_key, recent_activities, timeout=300)  # 5 minutes
        
    except Exception as e:
        print(f"Failed to log activity: {e}")

def send_notification_email(user_email, subject, message):
    """Send notification email to user"""
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user_email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def process_face_recognition(username, face_data):
    """Process face recognition using OpenCV"""
    try:
        # This is a simplified implementation
        # In production, you would use a proper face recognition library
        
        # Get stored face data for user
        stored_biometric = BiometricData.objects(
            user_id__username=username,
            biometric_type='face',
            is_active=True
        ).first()
        
        if not stored_biometric:
            return {'success': False, 'error': 'No face data found'}
        
        # Compare face data (simplified)
        # In production, you would use proper face comparison algorithms
        stored_face = stored_biometric.biometric_data.decode('utf-8')
        
        # Simple comparison (replace with actual face recognition)
        similarity = compare_face_data(face_data, stored_face)
        
        if similarity > 0.8:  # 80% similarity threshold
            return {'success': True}
        else:
            return {'success': False, 'error': 'Face not recognized'}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}

def process_fingerprint_auth(username, fingerprint_data):
    """Process fingerprint authentication"""
    try:
        # Get stored fingerprint data for user
        stored_biometric = BiometricData.objects(
            user_id__username=username,
            biometric_type='fingerprint',
            is_active=True
        ).first()
        
        if not stored_biometric:
            return {'success': False, 'error': 'No fingerprint data found'}
        
        # Compare fingerprint data (simplified)
        stored_fingerprint = stored_biometric.biometric_data.decode('utf-8')
        
        # Simple comparison (replace with actual fingerprint matching)
        similarity = compare_fingerprint_data(fingerprint_data, stored_fingerprint)
        
        if similarity > 0.9:  # 90% similarity threshold
            return {'success': True}
        else:
            return {'success': False, 'error': 'Fingerprint not recognized'}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}

def compare_face_data(face1, face2):
    """Compare two face data strings (simplified)"""
    # This is a placeholder implementation
    # In production, use proper face recognition libraries
    import difflib
    
    similarity = difflib.SequenceMatcher(None, face1, face2).ratio()
    return similarity

def compare_fingerprint_data(fp1, fp2):
    """Compare two fingerprint data strings (simplified)"""
    # This is a placeholder implementation
    # In production, use proper fingerprint matching algorithms
    import difflib
    
    similarity = difflib.SequenceMatcher(None, fp1, fp2).ratio()
    return similarity

def get_user_statistics(user_id):
    """Get user statistics"""
    try:
        user_files = FileUpload.objects(user_id=user_id)
        
        stats = {
            'total_files': user_files.count(),
            'approved_files': user_files(status='approved').count(),
            'pending_files': user_files(status='pending').count(),
            'rejected_files': user_files(status='rejected').count(),
            'total_downloads': sum(f.download_count for f in user_files),
            'recent_uploads': user_files.order_by('-uploaded_at')[:5]
        }
        
        return stats
    
    except Exception as e:
        print(f"Failed to get user statistics: {e}")
        return {}

def get_system_statistics():
    """Get system-wide statistics"""
    try:
        stats = {
            'total_users': User.objects.count(),
            'total_files': FileUpload.objects().count(),
            'approved_files': FileUpload.objects(status='approved').count(),
            'pending_files': FileUpload.objects(status='pending').count(),
            'rejected_files': FileUpload.objects(status='rejected').count(),
            'total_downloads': sum(f.download_count for f in FileUpload.objects()),
            'recent_activities': UserActivity.objects().order_by('-timestamp')[:10]
        }
        
        return stats
    
    except Exception as e:
        print(f"Failed to get system statistics: {e}")
        return {}

def cleanup_old_files():
    """Clean up files older than specified days"""
    try:
        cutoff_date = timezone.now() - timedelta(days=30)
        
        # Find files older than 30 days
        old_files = FileUpload.objects(uploaded_at__lt=cutoff_date)
        
        deleted_count = 0
        for file_record in old_files:
            try:
                # Delete physical file
                if os.path.exists(file_record.file_path):
                    os.remove(file_record.file_path)
                
                # Delete database record
                file_record.delete()
                deleted_count += 1
                
            except Exception as e:
                print(f"Failed to delete file {file_record.id}: {e}")
        
        return deleted_count
    
    except Exception as e:
        print(f"Failed to cleanup old files: {e}")
        return 0

def generate_unique_filename(original_filename):
    """Generate unique filename to prevent conflicts"""
    file_extension = os.path.splitext(original_filename)[1]
    unique_id = str(uuid.uuid4())
    return f"{unique_id}{file_extension}"

def validate_image_file(uploaded_file):
    """Validate uploaded image file"""
    try:
        # Check if it's actually an image
        file_type = magic.from_buffer(uploaded_file.read(1024), mime=True)
        uploaded_file.seek(0)
        
        if not file_type.startswith('image/'):
            return False, "File is not an image"
        
        # Check image dimensions
        if file_type in ['image/jpeg', 'image/png']:
            from PIL import Image
            img = Image.open(uploaded_file)
            width, height = img.size
            
            if width > 5000 or height > 5000:
                return False, "Image dimensions too large"
        
        return True, "Valid image"
    
    except Exception as e:
        return False, f"Image validation failed: {e}"

def create_thumbnail(image_path, thumbnail_path, size=(200, 200)):
    """Create thumbnail from image"""
    try:
        from PIL import Image
        
        with Image.open(image_path) as img:
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(thumbnail_path, 'JPEG', quality=85)
        
        return True
    
    except Exception as e:
        print(f"Failed to create thumbnail: {e}")
        return False

def get_file_icon(file_type):
    """Get appropriate icon for file type"""
    icon_map = {
        'PDF': 'fas fa-file-pdf',
        'DOC': 'fas fa-file-word',
        'DOCX': 'fas fa-file-word',
        'PPT': 'fas fa-file-powerpoint',
        'PPTX': 'fas fa-file-powerpoint',
        'TXT': 'fas fa-file-alt',
        'ZIP': 'fas fa-file-archive',
        'UNKNOWN': 'fas fa-file'
    }
    
    return icon_map.get(file_type.upper(), 'fas fa-file')

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.1f} {size_names[i]}"

def get_user_ip_address(request):
    """Get user's IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def is_valid_email(email):
    """Validate email address format"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def generate_password_reset_token(user):
    """Generate password reset token"""
    import secrets
    token = secrets.token_urlsafe(32)
    
    # Store token in cache
    cache_key = f'password_reset_{user.id}'
    cache.set(cache_key, token, timeout=3600)  # 1 hour
    
    return token

def verify_password_reset_token(user_id, token):
    """Verify password reset token"""
    cache_key = f'password_reset_{user_id}'
    stored_token = cache.get(cache_key)
    
    return stored_token == token

def create_user_session(user, request):
    """Create user session with additional data"""
    request.session['user_id'] = str(user.id)
    request.session['username'] = user.username
    request.session['user_role'] = user.role
    request.session['is_authenticated'] = True
    request.session.set_expiry(86400)  # 24 hours

def destroy_user_session(request):
    """Destroy user session"""
    request.session.flush()
    request.session.clear_expired()

def get_popular_files(limit=10):
    """Get popular files based on download count"""
    try:
        popular_files = FileUpload.objects(
            status='approved'
        ).order_by('-download_count')[:limit]
        
        return list(popular_files)
    
    except Exception as e:
        print(f"Failed to get popular files: {e}")
        return []

def get_recent_files(limit=10):
    """Get recent approved files"""
    try:
        recent_files = FileUpload.objects(
            status='approved'
        ).order_by('-uploaded_at')[:limit]
        
        return list(recent_files)
    
    except Exception as e:
        print(f"Failed to get recent files: {e}")
        return []

def search_files(query, user=None):
    """Search files based on query"""
    try:
        search_filter = (
            MongoQ(title__icontains=query) |
            MongoQ(description__icontains=query) |
            MongoQ(subject__icontains=query) |
            MongoQ(tags__icontains=query)
        )
        
        if user and user.role == 'admin':
            files = FileUpload.objects(search_filter)
        else:
            files = FileUpload.objects(
                search_filter & MongoQ(status='approved')
            )
        
        return list(files.order_by('-uploaded_at'))
    
    except Exception as e:
        print(f"Failed to search files: {e}")
        return []

def backup_database():
    """Create database backup"""
    try:
        from django.core.management import call_command
        import io
        import sys
        
        # Capture command output
        out = io.StringIO()
        call_command('dumpdata', stdout=out)
        
        backup_data = out.getvalue()
        
        # Save backup to file
        backup_filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        backup_path = os.path.join(settings.MEDIA_ROOT, 'backups', backup_filename)
        
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        
        with open(backup_path, 'w') as f:
            f.write(backup_data)
        
        return backup_path
    
    except Exception as e:
        print(f"Failed to create backup: {e}")
        return None
