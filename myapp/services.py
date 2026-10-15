"""Service (business logic) layer for the public-facing site.

Thin functions over the models. Views validate input with forms, call these
functions, and redirect/render. Rule of thumb: anything that mutates state,
calls more than one model, or could be triggered by the API (later) lives here.
"""
from django.contrib import messages as dj_messages

from .models import Inquiry


def accept_contact_inquiry(cleaned_data, files=None):
    """Persist a validated contact-form submission and return the Inquiry.

    Centralizing this (rather than `form.save()`) means the same code path
    is used by the view and (later) by the API/CLI.
    """
    files = files or {}
    inquiry = Inquiry.objects.create(
        name=cleaned_data['name'],
        email=cleaned_data['email'],
        phone=cleaned_data.get('phone'),
        service=cleaned_data.get('service'),
        service_title=cleaned_data.get('service_title', ''),
        note=cleaned_data.get('note'),
    )
    # Populate service_title when the form didn't (e.g. phone/admin usage).
    if inquiry.service_id and not inquiry.service_title:
        inquiry.service_title = inquiry.service.title
        inquiry.save(update_fields=['service_title'])
    return inquiry


def transition_status(inquiry, target_status):
    """Move an inquiry to a status and stamp responded_at.

    Keeping transitions here (instead of inline in the view) keeps the
    responded_at invariant defined in Inquiry.save() without duplicating it.
    """
    inquiry.status = target_status
    inquiry.save()  # Inquiry.save() maintains responded_at snapshot
    return inquiry


def delete_inquiry(inquiry):
    inquiry.delete()