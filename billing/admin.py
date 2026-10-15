from django.contrib import admin
from .models import (
    Invoice, InvoiceLine, NumberSequence, Payment, PaymentAttempt,
    Proposal, ProposalLine, WebhookEvent,
)


@admin.register(NumberSequence)
class NumberSequenceAdmin(admin.ModelAdmin):
    list_display = ('domain', 'year', 'last')
    ordering = ('-year', 'domain')


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 1


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('number', 'client', 'status', 'total', 'paid_total', 'created_at')
    list_filter = ('status', 'currency')
    search_fields = ('number', 'client__user__username')
    inlines = [InvoiceLineInline]
    readonly_fields = ('number', 'subtotal', 'tax_total', 'total', 'paid_total')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('number', 'invoice', 'client', 'amount', 'method', 'status', 'paid_at')
    list_filter = ('method', 'status')
    search_fields = ('number', 'reference', 'gateway_trx_id')


admin.site.register(Proposal)
admin.site.register(ProposalLine)
admin.site.register(PaymentAttempt)
admin.site.register(WebhookEvent)