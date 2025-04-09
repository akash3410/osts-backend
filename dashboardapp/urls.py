from django.urls import path
from .import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('services/', views.service_view, name='service'),
    path('add-service/', views.add_service, name='addservice'),
    path('edit-service/<int:pk>', views.edit_service, name='editservice'),
    path('delete-service/<int:pk>', views.delete_service, name='deleteservice'),
    path('sites-info/', views.sites_info_view, name='siteinfo'),
    path('messages/', views.all_message_view, name='allmessage'),
    path('response-update/<int:pk>', views.response_update_view, name='responseupdate'),
    path('message-delete/<int:pk>', views.message_delete_view, name='messagedelete'),
]