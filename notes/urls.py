from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('admin-login/', views.admin_login_view, name='admin_login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('admin-activities/', views.admin_activities, name='admin_activities'),
    path('upload/', views.upload_note, name='upload'),
    path('approve/<str:file_id>/', views.approve_note, name='approve_note'),
    path('delete/<str:file_id>/', views.delete_note, name='delete_note'),
    path('profile/', views.profile_view, name='profile'),
    path('biometric-login/', views.biometric_login_check, name='biometric_login'),
    path('enroll-biometric/', views.enroll_biometric, name='enroll_biometric'),
    # WebAuthn endpoints
    path('webauthn/register/begin/', views.webauthn_register_begin, name='webauthn_register_begin'),
    path('webauthn/register/complete/', views.webauthn_register_complete, name='webauthn_register_complete'),
    path('webauthn/login/begin/', views.webauthn_login_begin, name='webauthn_login_begin'),
    path('webauthn/login/complete/', views.webauthn_login_complete, name='webauthn_login_complete'),
    # Face recognition login
    path('face-login/', views.face_login, name='face_login'),
    path('face-enroll/', views.face_enroll, name='face_enroll'),
]
