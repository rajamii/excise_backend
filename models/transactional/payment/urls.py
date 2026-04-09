from django.urls import path

from .views import wallet_summary, wallet_recharge_list, wallet_history_list

app_name = "payment"

urlpatterns = [
    # path("master-data/", views.payment_master_data, name="master-data"),
    # path("modules/<str:module_code>/hoas/", views.payment_module_hoas, name="module-hoas"),
    # 
    # license_id values can contain "/" (e.g. NA/03/2025-26/0001),
    # so wallet routes must use <path:...>.
    # Keep specific routes above generic wallet-balance route.
    path("wallet/<path:licensee_id>/summary/", wallet_summary, name="wallet-summary"),
    path("wallet/<path:licensee_id>/recharge/", wallet_recharge_list, name="wallet-recharge-list"),
    path("wallet/<path:licensee_id>/history/", wallet_history_list, name="wallet-history-list"),
    # path("wallet/<path:licensee_id>/", views.payment_wallet_balance, name="wallet-balance"),
    # path("transactions/", views.payment_transaction_list, name="transaction-list"),
    # path("transactions/initiate/", views.payment_initiate, name="transaction-initiate"),
    # path("transactions/<str:utr>/", views.payment_transaction_detail, name="transaction-detail"),
    # path(
    #     "transactions/<str:utr>/status/",
    #     views.payment_update_status,
    #     name="transaction-update-status",
    # ),
]
