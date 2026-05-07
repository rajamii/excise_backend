from django.urls import path

from .views import wallet_history_list, wallet_recharge_credit, wallet_recharge_list, wallet_summary

app_name = "payment"

urlpatterns = [
    # license_id values can contain "/" (e.g. NA/03/2025-26/0001), so wallet routes must use <path:...>.
    path("wallet/<path:licensee_id>/summary/", wallet_summary, name="wallet-summary"),
    path("wallet/<path:licensee_id>/recharge/credit/", wallet_recharge_credit, name="wallet-recharge-credit"),
    path("wallet/<path:licensee_id>/recharge/", wallet_recharge_list, name="wallet-recharge-list"),
    path("wallet/<path:licensee_id>/history/", wallet_history_list, name="wallet-history-list"),
]

