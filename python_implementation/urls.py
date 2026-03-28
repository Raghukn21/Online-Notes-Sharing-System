from django.urls import path
from . import views

urlpatterns = [
    # Home and Authentication
    path('', views.index, name='index'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Dashboard and File Management
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('upload/', views.upload_note, name='upload'),
    
    # Admin Functions
    path('admin-activities/', views.admin_activities, name='admin_activities'),
    path('approve/<str:file_id>/', views.approve_note, name='approve_note'),
    path('delete/<str:file_id>/', views.delete_note, name='delete_note'),
    
    # Profile Management
    path('profile/', views.profile_view, name='profile'),
    
    # Biometric Authentication
    path('biometric-login/', views.biometric_login_check, name='biometric_login'),
    path('enroll-biometric/', views.enroll_biometric, name='enroll_biometric'),
    
    # WebAuthn endpoints
    path('webauthn/register/begin/', views.webauthn_register_begin, name='webauthn_register_begin'),
    path('webauthn/register/complete/', views.webauthn_register_complete, name='webauthn_register_complete'),
    path('webauthn/login/begin/', views.webauthn_login_begin, name='webauthn_login_begin'),
    path('webauthn/login/complete/', views.webauthn_login_complete, name='webauthn_login_complete'),
    
    # Face recognition endpoints
    path('face-login/', views.face_login, name='face_login'),
    path('face-enroll/', views.face_enroll, name='face_enroll'),
    
    # API endpoints
    path('api/files/', views.api_files, name='api_files'),
    path('api/download/<str:file_id>/', views.api_download_file, name='api_download_file'),
]
