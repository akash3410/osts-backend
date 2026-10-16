from django.urls import path

from .views import (
    _mock_pay_view,
    invoice_detail_view,
    invoice_list_view,
    payment_initiate_view,
    sslcommerz_webhook_view,
    sslcommerz_return_view,
)

app_name = 'billing'

urlpatterns = [
    path('invoices/', invoice_list_view, name='invoice_list'),
    path('invoices/<int:pk>/', invoice_detail_view, name='invoice_detail'),
    path('invoices/<int:invoice_id>/pay/', payment_initiate_view, name='payment_initiate'),
    path('webhook/sslcommerz/', sslcommerz_webhook_view, name='sslcommerz_webhook'),
    path('sslcommerz/return/', sslcommerz_return_view, name='sslcommerz_return'),
    # Dev-only mock gateway auto-submit form.
    path('mock-pay/<uuid:txid>/', _mock_pay_view, name='mock_pay'),
]