from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from mongoengine import Document, EmbeddedDocument, fields
import uuid
import os

class User(AbstractUser):
    """Extended User model with additional fields"""
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('admin', 'Administrator'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'role']
    
    class Meta:
        db_table = 'auth_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

class BiometricData(Document):
    """MongoDB document for storing biometric data"""
    user_id = fields.UUIDField(required=True)
    biometric_type = fields.StringField(choices=['face', 'fingerprint'], required=True)
    biometric_data = fields.BinaryField(required=True)
    created_at = fields.DateTimeField(default=timezone.now)
    is_active = fields.BooleanField(default=True)
    
    meta = {
        'collection': 'biometric_data',
        'indexes': [
            'user_id',
            'biometric_type',
            'created_at'
        ]
    }

class FileUpload(Document):
    """MongoDB document for file uploads"""
    STATUS_CHOICES = ['pending', 'approved', 'rejected']
    
    id = fields.StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = fields.UUIDField(required=True)
    username = fields.StringField(required=True)
    user_role = fields.StringField(required=True)
    
    # File Information
    filename = fields.StringField(required=True)
    original_filename = fields.StringField(required=True)
    file_path = fields.StringField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StringField(required=True)
    mime_type = fields.StringField(required=True)
    file_hash = fields.StringField(required=True)
    
    # Metadata
    title = fields.StringField(required=True)
    description = fields.StringField()
    subject = fields.StringField()
    tags = fields.ListField(fields.StringField())
    
    # Status and Approval
    status = fields.StringField(choices=STATUS_CHOICES, default='pending')
    approved_by = fields.UUIDField()
    approved_at = fields.DateTimeField()
    rejection_reason = fields.StringField()
    
    # Timestamps
    uploaded_at = fields.DateTimeField(default=timezone.now)
    updated_at = fields.DateTimeField(default=timezone.now)
    download_count = fields.IntField(default=0)
    
    # Activity tracking
    last_accessed = fields.DateTimeField()
    
    meta = {
        'collection': 'file_uploads',
        'indexes': [
            'user_id',
            'username',
            'status',
            'uploaded_at',
            'subject',
            'tags'
        ]
    }
    
    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.filename} ({self.status})"

class UserActivity(Document):
    """MongoDB document for tracking user activities"""
    ACTIVITY_TYPES = [
        'login', 'logout', 'upload', 'download', 
        'delete', 'approve', 'reject', 'profile_update'
    ]
    
    id = fields.StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = fields.UUIDField(required=True)
    username = fields.StringField(required=True)
    user_role = fields.StringField(required=True)
    
    activity_type = fields.StringField(choices=ACTIVITY_TYPES, required=True)
    description = fields.StringField(required=True)
    ip_address = fields.StringField()
    user_agent = fields.StringField()
    
    # Additional activity data
    file_id = fields.StringField()
    metadata = fields.DictField()
    
    timestamp = fields.DateTimeField(default=timezone.now)
    
    meta = {
        'collection': 'user_activities',
        'indexes': [
            'user_id',
            'username',
            'activity_type',
            'timestamp'
        ]
    }
    
    def __str__(self):
        return f"{self.username} - {self.activity_type} at {self.timestamp}"

class SystemSettings(Document):
    """MongoDB document for system settings"""
    key = fields.StringField(required=True, unique=True)
    value = fields.DynamicField(required=True)
    description = fields.StringField()
    created_at = fields.DateTimeField(default=timezone.now)
    updated_at = fields.DateTimeField(default=timezone.now)
    
    meta = {
        'collection': 'system_settings',
        'indexes': ['key']
    }
    
    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Get setting value by key"""
        setting = cls.objects(key=key).first()
        return setting.value if setting else default
    
    @classmethod
    def set_setting(cls, key, value, description=None):
        """Set setting value"""
        setting = cls.objects(key=key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = cls(key=key, value=value, description=description)
        setting.save()
        return setting

# Django Models for Admin Interface
class UserProfile(models.Model):
    """Django model for user profile (for admin interface)"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='userprofile')
    bio = models.TextField(max_length=500, blank=True)
    website = models.URLField(blank=True)
    location = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"

class FileApprovalLog(models.Model):
    """Django model for file approval logs (for admin interface)"""
    file_id = models.CharField(max_length=36, unique=True)
    approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=[('approved', 'Approved'), ('rejected', 'Rejected')])
    reason = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.file_id} - {self.action} by {self.approver}"
