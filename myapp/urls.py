from django.urls import path
from . import views
urlpatterns = [
    path('', views.home_view, name='homepage'),
    path('about/', views.about_view, name='aboutpage'),
    path('services/', views.service_view, name='servicepage'),
    path('contacts/', views.contact_view, name='contactepage'),
]