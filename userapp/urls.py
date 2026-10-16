from django.urls import path
from .import views

urlpatterns = [
    path('profile/', views.profile_view, name="profile"),
    path('check-username/', views.check_username, name="check_username"),
    path('auth/', views.auth_page, name="auth"),
    path('register/', views.register_view, name="register"),
    path('login/', views.login_view, name="login"),
    path('logout/', views.logout_view, name="logout"),
    path('user-info/', views.edit_user_info, name="EditUserInfo"),
]