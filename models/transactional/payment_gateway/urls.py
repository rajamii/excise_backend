from django.urls import path

from . import views

app_name = "payment_gateway"

urlpatterns = [
    path("modules/<str:module_code>/", views.get_payment_module, name="payment-module-detail"),
    path("billdesk/initiate/", views.billdesk_initiate_wallet_recharge, name="billdesk-initiate"),
    path("billdesk/initiate/license-fee/", views.billdesk_initiate_license_fee, name="billdesk-initiate-license-fee"),
    path("billdesk/initiate/security-deposit/", views.billdesk_initiate_security_deposit, name="billdesk-initiate-security-deposit"),
    path("billdesk/initiate/new-license-application-fee/", views.billdesk_initiate_new_license_application_fee, name="billdesk-initiate-new-license-application-fee"),
    path("billdesk/response/", views.billdesk_response, name="billdesk-response"),
    path("billdesk/webhook/", views.billdesk_webhook, name="billdesk-webhook"),
    path("billdesk/transactions/", views.list_billdesk_transactions, name="billdesk-transactions-list"),
    path("billdesk/check-wallet-status/<str:transaction_id>/", views.billdesk_check_wallet_payment_status, name="billdesk-check-wallet-status"),
    path("billdesk/simulate-wallet-recharge/", views.billdesk_simulate_wallet_recharge, name="billdesk-simulate-wallet-recharge"),
    path("revenue-receipts/", views.revenue_receipts_chart_data, name="revenue-receipts-chart-data"),
    # path("billdesk/mock/process/", views.billdesk_mock_process, name="billdesk-mock-process"),
]
