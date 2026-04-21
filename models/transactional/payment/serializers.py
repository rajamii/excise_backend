from decimal import Decimal

from rest_framework import serializers

from .models import (
    # PaymentBilldeskTransaction,
    # PaymentGatewayParameter,
    # PaymentHeadOfAccount,
    # PaymentModule,
    # PaymentModuleHoa,
    # PaymentWalletMaster,
    WalletBalance,
    WalletTransaction,
)


# class PaymentGatewayParameterSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = PaymentGatewayParameter
#         fields = "__all__"


# class PaymentModuleSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = PaymentModule
#         fields = "__all__"


# class PaymentHeadOfAccountSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = PaymentHeadOfAccount
#         fields = "__all__"


# class PaymentModuleHoaSerializer(serializers.ModelSerializer):
#     module_code = serializers.CharField(source="module_code.module_code", read_only=True)
#     head_of_account = serializers.CharField(source="head_of_account.head_of_account", read_only=True)
#     hoa_description = serializers.CharField(
#         source="head_of_account.detailed_head_driscription", read_only=True
#     )

#     class Meta:
#         model = PaymentModuleHoa
#         fields = (
#             "id",
#             "module_code",
#             "head_of_account",
#             "hoa_description",
#             "is_active",
#             "user_id",
#             "opr_date",
#             "created_date",
        # )


# class PaymentWalletMasterSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = PaymentWalletMaster
#         fields = "__all__"


# class PaymentBilldeskTransactionSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = PaymentBilldeskTransaction
#         fields = "__all__"


class WalletBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletBalance
        fields = "__all__"


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = "__all__"


class WalletRechargeCreditSerializer(serializers.Serializer):
    transaction_id = serializers.CharField(max_length=100)
    wallet_type = serializers.CharField(max_length=30)
    head_of_account = serializers.CharField(max_length=50)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    remarks = serializers.CharField(max_length=300, required=False, allow_blank=True)

class PaymentItemSerializer(serializers.Serializer):
    head_of_account = serializers.CharField(max_length=50)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))


class PaymentInitiateSerializer(serializers.Serializer):
    payment_module_code = serializers.CharField(max_length=20)
    payer_id = serializers.CharField(max_length=50)
    items = PaymentItemSerializer(many=True)
    gateway_sl_no = serializers.IntegerField(required=False)
    requisition_id_no = serializers.CharField(max_length=50, required=False, allow_blank=True)
    user_id = serializers.CharField(max_length=50, required=False, allow_blank=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one HOA item is required.")
        return value


class PaymentStatusUpdateSerializer(serializers.Serializer):
    payment_status = serializers.ChoiceField(choices=("P", "S", "F"))
    response_authstatus = serializers.CharField(max_length=10, required=False, allow_blank=True)
    response_errorstatus = serializers.CharField(max_length=50, required=False, allow_blank=True)
    response_errordescription = serializers.CharField(
        max_length=500, required=False, allow_blank=True
    )
    response_string = serializers.CharField(required=False, allow_blank=True)
    response_txnreferenceno = serializers.CharField(max_length=100, required=False, allow_blank=True)
    response_bankreferenceno = serializers.CharField(max_length=100, required=False, allow_blank=True)
    response_txnamount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False
    )
    response_txndate = serializers.DateTimeField(required=False)
