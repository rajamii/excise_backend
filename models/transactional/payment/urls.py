from django.urls import path

from . import views

app_name = "payment"

urlpatterns = [
    path("master-data/", views.payment_master_data, name="master-data"),
    path("modules/<str:module_code>/hoas/", views.payment_module_hoas, name="module-hoas"),
    path("wallet/<str:licensee_id>/", views.payment_wallet_balance, name="wallet-balance"),
    path("transactions/", views.payment_transaction_list, name="transaction-list"),
    path("transactions/initiate/", views.payment_initiate, name="transaction-initiate"),
    path("transactions/<str:utr>/", views.payment_transaction_detail, name="transaction-detail"),
    path(
        "transactions/<str:utr>/status/",
        views.payment_update_status,
        name="transaction-update-status",
    ),
]
