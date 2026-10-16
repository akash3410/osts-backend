from django.contrib import admin

from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "template", "title", "email_sent", "created_at")
    list_filter = ("template", "email_sent", "created_at")
    search_fields = ("user__username", "title", "body")
    readonly_fields = ("created_at",)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "invoice_sent", "invoice_paid", "invoice_overdue", "marketing")
    list_editable = ("invoice_sent", "invoice_paid", "invoice_overdue", "marketing")
    search_fields = ("user__username",)
