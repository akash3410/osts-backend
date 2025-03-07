from django.urls import path
from .import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('services/', views.service_view, name='service'),
    path('add-service/', views.add_service, name='addservice'),
    path('edit-service/<int:pk>', views.edit_service, name='editservice'),
    path('delete-service/<int:pk>', views.delete_service, name='deleteservice'),
]