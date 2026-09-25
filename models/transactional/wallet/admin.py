from django.contrib import admin
from .models import SecurityDepositRecord, WalletBalance, WalletTransaction, MasterWalletType


@admin.register(SecurityDepositRecord)
class SecurityDepositRecordAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "application_id",
        "username",
        "applicant_name",
        "establishment_name",
        "license_id",
        "amount",
        "refunded_amount",
        "balance_amount",
        "status",
        "from_date",
        "to_date",
        "deposit_duration_days",
        "payment_date",
        "transaction_id",
    ]
    list_filter = ["status", "from_date", "to_date", "payment_date", "created_at"]
    search_fields = [
        "application_id",
        "username",
        "applicant_name",
        "license_id",
        "transaction_id",
        "reference_no",
        "establishment_name",
    ]
    readonly_fields = ["created_at", "updated_at", "balance_amount", "deposit_duration_days"]
    fieldsets = (
        (
            "Application & User Info",
            {
                "fields": (
                    "application_id",
                    "user",
                    "applicant_user_id",
                    "username",
                    "applicant_name",
                    "establishment_name",
                    "license_id",
                )
            },
        ),
        (
            "Deposit & Duration Period",
            {
                "fields": (
                    "from_date",
                    "to_date",
                    "deposit_duration_days",
                )
            },
        ),
        (
            "Payment & Deposit Details",
            {
                "fields": (
                    "amount",
                    "refunded_amount",
                    "balance_amount",
                    "status",
                    "payment_date",
                    "transaction_id",
                    "reference_no",
                    "remarks",
                )
            },
        ),
        (
            "Audit Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(WalletBalance)
class WalletBalanceAdmin(admin.ModelAdmin):
    list_display = [
        "wallet_balance_id",
        "licensee_id",
        "licensee_name",
        "wallet_type",
        "head_of_account",
        "current_balance",
        "total_credit",
        "total_debit",
        "last_updated_at",
    ]
    search_fields = ["licensee_id", "licensee_name", "user_id", "head_of_account"]
    list_filter = ["wallet_type", "module_type"]


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "wallet_transaction_id",
        "transaction_id",
        "licensee_id",
        "wallet_type",
        "entry_type",
        "transaction_type",
        "amount",
        "balance_after",
        "payment_status",
        "created_at",
    ]
    search_fields = ["transaction_id", "licensee_id", "reference_no", "user_id"]
    list_filter = ["wallet_type", "entry_type", "transaction_type", "payment_status"]


@admin.register(MasterWalletType)
class MasterWalletTypeAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "is_active"]
