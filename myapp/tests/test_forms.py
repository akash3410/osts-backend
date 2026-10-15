"""Tests for the public contact/quote form (MessageForm).

Covers the honeypot anti-spam layer added in Phase 1.
"""

import pytest

from myapp.forms import HONEYPOT_FIELD, MessageForm
from myapp.models import Messages

pytestmark = pytest.mark.django_db


def _base_payload(service):
    return {
        "name": "Human User",
        "email": "human@example.com",
        "phone": "+8801711111111",
        "service": str(service.pk),
        "note": "I'd like a quote.",
    }


class TestMessageFormHoneypot:
    """The hidden `website_url` field catches bots but not humans."""

    def test_human_submission_without_honeypot_is_valid(self, service):
        form = MessageForm(data=_base_payload(service))
        assert form.is_valid(), form.errors

    def test_empty_honeypot_is_valid(self, service):
        form = MessageForm(data={**_base_payload(service), HONEYPOT_FIELD: ""})
        assert form.is_valid(), form.errors

    def test_filled_honeypot_is_rejected(self, service):
        form = MessageForm(
            data={**_base_payload(service), HONEYPOT_FIELD: "http://spam.example"}
        )
        assert not form.is_valid()
        assert HONEYPOT_FIELD in form.errors

    def test_filled_honeypot_does_not_create_a_row(self, service):
        before = Messages.objects.count()
        form = MessageForm(
            data={**_base_payload(service), HONEYPOT_FIELD: "http://spam.example"}
        )
        if form.is_valid():
            form.save()
        assert Messages.objects.count() == before

    def test_honeypot_field_is_not_a_model_field(self):
        # It must never be persisted — it isn't part of the model.
        assert HONEYPOT_FIELD not in Messages._meta.fields

    def test_honeypot_renders_hidden_widget(self, service):
        form = MessageForm()
        widget_attrs = form.fields[HONEYPOT_FIELD].widget.attrs
        # Hidden from humans via CSS + removed from tab order + a11y-hidden.
        assert "display:none" in widget_attrs.get("style", "")
        assert widget_attrs.get("tabindex") == "-1"
        assert widget_attrs.get("aria-hidden") == "true"

    def test_legitimate_submission_saves(self, service):
        form = MessageForm(data=_base_payload(service))
        assert form.is_valid(), form.errors
        obj = form.save()
        assert obj.pk is not None
        assert obj.name == "Human User"
