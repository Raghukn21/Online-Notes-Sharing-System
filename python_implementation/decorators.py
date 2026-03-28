from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from django.core.cache import cache
import time

def role_required(allowed_roles):
    """
    Decorator to restrict access based on user role
    Usage: @role_required(['admin', 'teacher'])
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': 'Permission denied'}, status=403)
                else:
                    messages.error(request, 'You do not have permission to access this page.')
                    return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def admin_required(view_func):
    """Decorator to restrict access to admin users only"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'admin':
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Admin access required'}, status=403)
            else:
                messages.error(request, 'Admin access required.')
                return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper

def teacher_required(view_func):
    """Decorator to restrict access to teacher users only"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ['teacher', 'admin']:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Teacher access required'}, status=403)
            else:
                messages.error(request, 'Teacher access required.')
                return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper

def verified_user_required(view_func):
    """Decorator to require email verification"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_verified:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Email verification required'}, status=403)
            else:
                messages.error(request, 'Please verify your email address.')
                return redirect('profile')
        return view_func(request, *args, **kwargs)
    return wrapper

def rate_limit(limit=5, window=60):
    """
    Rate limiting decorator
    limit: number of requests allowed
    window: time window in seconds
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Get client IP
            ip_address = request.META.get('REMOTE_ADDR')
            cache_key = f'rate_limit_{ip_address}'
            
            # Get current count
            current_count = cache.get(cache_key, 0)
            
            if current_count >= limit:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': 'Rate limit exceeded'}, status=429)
                else:
                    messages.error(request, 'Too many requests. Please try again later.')
                    return redirect('dashboard')
            
            # Increment count
            cache.set(cache_key, current_count + 1, window)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def ajax_required(view_func):
    """Decorator to require AJAX requests"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
            return JsonResponse({'error': 'AJAX request required'}, status=400)
        return view_func(request, *args, **kwargs)
    return wrapper

def superuser_or_admin(view_func):
    """Decorator to require superuser or admin role"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.role == 'admin'):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Superuser or admin access required'}, status=403)
            else:
                messages.error(request, 'Superuser or admin access required.')
                return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper

def prevent_cache(view_func):
    """Decorator to prevent browser caching"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
    return wrapper

def require_http_methods(*methods):
    """Decorator to require specific HTTP methods"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': f'Method {request.method} not allowed'}, status=405)
                else:
                    messages.error(request, f'Method {request.method} not allowed.')
                    return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def file_owner_or_admin(view_func):
    """Decorator to require file owner or admin access"""
    @wraps(view_func)
    @login_required
    def wrapper(request, file_id, *args, **kwargs):
        from .models import FileUpload
        
        try:
            file_record = FileUpload.objects.get(id=file_id)
            
            # Check if user is owner or admin
            if (request.user.role != 'admin' and 
                file_record.user_id != request.user.id):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': 'Permission denied'}, status=403)
                else:
                    messages.error(request, 'You do not have permission to access this file.')
                    return redirect('dashboard')
            
            # Add file record to request
            request.file_record = file_record
            
            return view_func(request, file_id, *args, **kwargs)
        
        except FileUpload.DoesNotExist:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'File not found'}, status=404)
            else:
                messages.error(request, 'File not found.')
                return redirect('dashboard')
    
    return wrapper
