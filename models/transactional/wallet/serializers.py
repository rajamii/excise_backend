from decimal import Decimal
from rest_framework import serializers
from .models import WalletBalance, WalletTransaction

class WalletBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletBalance
        fields = "__all__"
        read_only_fields = (
            "wallet_balance_id",
            "opening_balance",
            "total_credit",
            "total_debit",
            "current_balance",
            "last_updated_at",
            "created_at",
        )

class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = "__all__"
        read_only_fields = (
            "wallet_transaction_id",
            "balance_before",
            "balance_after",
            "created_at",
        )

class WalletRechargeCreditSerializer(serializers.Serializer):
    transaction_id = serializers.CharField(max_length=100)
    wallet_type = serializers.CharField(max_length=30)
    head_of_account = serializers.CharField(max_length=50)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    remarks = serializers.CharField(max_length=300, required=False, allow_blank=True)