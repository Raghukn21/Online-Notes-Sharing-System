from rest_framework import serializers
from .models import FileUpload, UserActivity

class FileUploadSerializer(serializers.Serializer):
    """Serializer for FileUpload documents"""
    id = serializers.CharField()
    user_id = serializers.UUIDField()
    username = serializers.CharField()
    user_role = serializers.CharField()
    
    # File Information
    filename = serializers.CharField()
    original_filename = serializers.CharField()
    file_size = serializers.IntegerField()
    file_type = serializers.CharField()
    mime_type = serializers.CharField()
    
    # Metadata
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    subject = serializers.CharField(allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField())
    
    # Status and Approval
    status = serializers.CharField()
    approved_by = serializers.UUIDField(allow_null=True)
    approved_at = serializers.DateTimeField(allow_null=True)
    rejection_reason = serializers.CharField(allow_blank=True)
    
    # Timestamps
    uploaded_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    download_count = serializers.IntegerField()
    last_accessed = serializers.DateTimeField(allow_null=True)

class UserActivitySerializer(serializers.Serializer):
    """Serializer for UserActivity documents"""
    id = serializers.CharField()
    user_id = serializers.UUIDField()
    username = serializers.CharField()
    user_role = serializers.CharField()
    
    activity_type = serializers.CharField()
    description = serializers.CharField()
    ip_address = serializers.CharField(allow_blank=True)
    user_agent = serializers.CharField(allow_blank=True)
    
    # Additional activity data
    file_id = serializers.CharField(allow_blank=True)
    metadata = serializers.DictField()
    
    timestamp = serializers.DateTimeField()

class BiometricDataSerializer(serializers.Serializer):
    """Serializer for BiometricData documents"""
    user_id = serializers.UUIDField()
    biometric_type = serializers.CharField()
    created_at = serializers.DateTimeField()
    is_active = serializers.BooleanField()

class SystemSettingsSerializer(serializers.Serializer):
    """Serializer for SystemSettings documents"""
    key = serializers.CharField()
    value = serializers.DynamicField()
    description = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

class UserStatisticsSerializer(serializers.Serializer):
    """Serializer for user statistics"""
    total_files = serializers.IntegerField()
    approved_files = serializers.IntegerField()
    pending_files = serializers.IntegerField()
    rejected_files = serializers.IntegerField()
    total_downloads = serializers.IntegerField()
    recent_uploads = FileUploadSerializer(many=True)

class SystemStatisticsSerializer(serializers.Serializer):
    """Serializer for system statistics"""
    total_users = serializers.IntegerField()
    total_files = serializers.IntegerField()
    approved_files = serializers.IntegerField()
    pending_files = serializers.IntegerField()
    rejected_files = serializers.IntegerField()
    total_downloads = serializers.IntegerField()
    recent_activities = UserActivitySerializer(many=True)
