"""Business-logic layer for dashboard staff operations.

Views are thin: validate with forms, delegate here, redirect/render.
"""
from .models import Service


def toggle_service_active(service):
    service.is_active = not service.is_active
    service.save(update_fields=['is_active'])
    return service


def delete_service(service):
    service.delete()


def list_services(search: str = ''):
    qs = Service.objects.all()
    if search:
        qs = qs.search(search)
    return qs.order_by('title')