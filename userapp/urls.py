from django.urls import path
from .import views

urlpatterns = [
    path('register/', views.register_view, name="register"),
    path('login/', views.login_view, name="login"),
    path('logout/', views.logout_view, name="logout"),
    path('user-info/', views.edit_user_info, name="EditUserInfo"),
]