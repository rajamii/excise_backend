from django.urls import path

from . import views

app_name = "payment_gateway"

urlpatterns = [
    path("billdesk/initiate/", views.billdesk_initiate_wallet_recharge, name="billdesk-initiate"),
    path("billdesk/initiate/license-fee/", views.billdesk_initiate_license_fee, name="billdesk-initiate-license-fee"),
    path("billdesk/initiate/security-deposit/", views.billdesk_initiate_security_deposit, name="billdesk-initiate-security-deposit"),
    path("billdesk/initiate/new-license-application-fee/", views.billdesk_initiate_new_license_application_fee, name="billdesk-initiate-new-license-application-fee"),
    path("billdesk/response/", views.billdesk_response, name="billdesk-response"),
    # path("billdesk/mock/process/", views.billdesk_mock_process, name="billdesk-mock-process"),
]
