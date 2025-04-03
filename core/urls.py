from django.urls import path
from .import views

urlpatterns = [
    path('site-config/', views.site_config, name='siteconfig')
]