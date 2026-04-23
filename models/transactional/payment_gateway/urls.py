from django.urls import path

from . import views

app_name = "payment_gateway"

urlpatterns = [
    path("billdesk/initiate/", views.billdesk_initiate_wallet_recharge, name="billdesk-initiate"),
    path("billdesk/response/", views.billdesk_response, name="billdesk-response"),
]

