from django.urls import path
from .import views

urlpatterns = [
    path('profile/', views.profile_view, name="profile"),
    path('check-username/', views.check_username, name="check_username"),
    path('verify-email/', views.verify_email_view, name="verify_email"),
    path('resend-code/', views.resend_code_view, name="resend_code"),
    path('forgot-password/', views.forgot_password_view, name="forgot_password"),
    path('reset-password/', views.reset_password_view, name="reset_password"),
    path('auth/', views.auth_page, name="auth"),
    path('register/', views.register_view, name="register"),
    path('login/', views.login_view, name="login"),
    path('logout/', views.logout_view, name="logout"),
    path('user-info/', views.edit_user_info, name="EditUserInfo"),
]