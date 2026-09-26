from django.urls import path

from .views import (
    wallet_history_list,
    wallet_recharge_credit,
    wallet_recharge_list,
    wallet_summary,
    security_deposit_record_list,
    deduct_security_deposit,
    refund_security_deposit,
)

app_name = "payment"

urlpatterns = [
    # Security Deposit Records
    path("security-deposit-records/", security_deposit_record_list, name="security-deposit-records-list"),
    path("security-deposit-records/<int:pk>/deduct/", deduct_security_deposit, name="security-deposit-record-deduct"),
    path("security-deposit-records/<int:pk>/refund/", refund_security_deposit, name="security-deposit-record-refund"),

    # license_id values can contain "/" (e.g. NA/03/2025-26/0001), so wallet routes must use <path:...>.
    path("wallet/<path:licensee_id>/summary/", wallet_summary, name="wallet-summary"),
    path("wallet/<path:licensee_id>/recharge/credit/", wallet_recharge_credit, name="wallet-recharge-credit"),
    path("wallet/<path:licensee_id>/recharge/", wallet_recharge_list, name="wallet-recharge-list"),
    path("wallet/<path:licensee_id>/history/", wallet_history_list, name="wallet-history-list"),
]

