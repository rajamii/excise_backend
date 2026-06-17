from django.urls import path
from . import views
from . import helpers

app_name = "payment_gateway"

urlpatterns = [
    path("modules/<str:module_code>/", helpers.get_payment_module, name="payment-module-detail"),
    
    # Wallet Recharge
    path("sbiepay/initiate/", views.sbiepay_initiate_wallet_recharge, name="sbiepay-initiate"),
    
    # License Fee
    path("sbiepay/initiate/license-fee/", views.sbiepay_initiate_license_fee, name="sbiepay-initiate-license-fee"),
    
    # Security Deposit
    path("sbiepay/initiate/security-deposit/", views.sbiepay_initiate_security_deposit, name="sbiepay-initiate-security-deposit"),
    
    # New License App Fee
    path("sbiepay/initiate/new-license-application-fee/", views.sbiepay_initiate_new_license_application_fee, name="sbiepay-initiate-new-license-application-fee"),
    
    # Global Callback
    path("sbiepay/response/", helpers.sbiepay_response, name="sbiepay-response"),
]