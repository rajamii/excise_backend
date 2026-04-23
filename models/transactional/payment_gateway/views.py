import hashlib
import hmac
from urllib.parse import urlencode
from decimal import Decimal

from django.conf import settings
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import PaymentBilldeskTransaction, PaymentGatewayParameters


def _billdesk_hmac_sha256(msg: str, key: str) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest().upper()


def _normalize_amount(raw_amount) -> Decimal:
    value = Decimal(str(raw_amount or "0")).quantize(Decimal("0.01"))
    if value <= 0:
        raise ValueError("amount must be greater than zero")
    return value


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billdesk_initiate_wallet_recharge(request):
    data = request.data or {}

    transaction_id = str(data.get("transaction_id") or "").strip()
    wallet_type = str(data.get("wallet_type") or "").strip()
    head_of_account = str(data.get("head_of_account") or "").strip()
    raw_amount = data.get("amount")

    if not transaction_id:
        return Response({"detail": "transaction_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not wallet_type:
        return Response({"detail": "wallet_type is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not head_of_account:
        return Response({"detail": "head_of_account is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        amount = _normalize_amount(raw_amount)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active="Y", payment_gateway_name__iexact="Billdesk")
        .order_by("sl_no")
        .first()
    )
    if gateway is None:
        return Response(
            {"detail": "No active Billdesk configuration found in Payment_Gateway_Parameters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    billdesk_url = getattr(settings, "BILLDESK_GATEWAY_URL", "") or ""
    if not billdesk_url:
        return Response(
            {"detail": "BILLDESK_GATEWAY_URL is not configured on server."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return_url = str(gateway.return_url or "").strip()
    if not return_url:
        return Response(
            {"detail": "return_url is not configured for Billdesk in Payment_Gateway_Parameters."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    merchant_id = str(gateway.merchantid or "").strip()
    security_id = str(gateway.securityid or "").strip()
    encryption_key = str(gateway.encryption_key or "").strip()
    if not merchant_id or not security_id or not encryption_key:
        return Response(
            {"detail": "Billdesk gateway config is missing merchantid/securityid/encryption_key."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    amount_str = f"{amount:.2f}"
    additional_info1 = head_of_account
    additional_info2 = "SIKPAY"
    # Keep walletType directly so the Angular success screen can display it as-is.
    additional_info3 = wallet_type

    msg_without_checksum = (
        f"{merchant_id}|{transaction_id}|NA|{amount_str}|NA|NA|NA|INR|NA|R|{security_id}|NA|NA|F|"
        f"{additional_info1}|{additional_info2}|{additional_info3}|NA|NA|NA|NA|{return_url}"
    )
    checksum = _billdesk_hmac_sha256(msg_without_checksum, encryption_key)
    request_msg = f"{msg_without_checksum}|{checksum}"

    PaymentBilldeskTransaction.objects.update_or_create(
        utr=transaction_id,
        defaults={
            "transaction_date": timezone.now(),
            "transaction_id_no_hoa": transaction_id,
            "payer_id": str(getattr(request.user, "username", "") or "").strip()[:50],
            "payment_module_code": "WALLET_RECHARGE",
            "transaction_amount": amount,
            "request_merchantid": merchant_id,
            "request_currencytype": "INR",
            "request_typefield1": "R",
            "request_securityid": security_id,
            "request_typefield2": "F",
            "request_additionalinfo1": additional_info1,
            "request_additionalinfo2": additional_info2,
            "request_additionalinfo3": additional_info3,
            "request_additionalinfo4": "NA",
            "request_additionalinfo5": "NA",
            "request_additionalinfo6": "NA",
            "request_additionalinfo7": "NA",
            "request_return_url": return_url,
            "request_checksum": checksum,
            "request_string": request_msg,
            "payment_status": "P",
            "opr_date": timezone.now(),
            "user_id": str(getattr(request.user, "username", "") or "").strip()[:50],
        },
    )

    return Response(
        {
            "billdesk_url": billdesk_url,
            "request_msg": request_msg,
            "transaction_id": transaction_id,
        }
    )


@csrf_exempt
def billdesk_response(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    response_msg = str(request.POST.get("msg") or "").strip()
    if not response_msg:
        response_msg = str(request.POST.get("MSG") or "").strip()
    if not response_msg:
        return HttpResponseBadRequest("Missing msg")

    parts = response_msg.split("|")
    if len(parts) < 3:
        return HttpResponseBadRequest("Invalid msg format")

    response_checksum = parts[-1].strip()
    msg_without_checksum = "|".join(parts[:-1])

    # BillDesk response format (typical):
    # MerchantID|CustomerID|TxnReferenceNo|BankReferenceNo|TxnAmount|BankID|BankMerchantID|TxnType|CurrencyName|ItemCode|
    # SecurityType|SecurityID|SecurityPassword|TxnDate|AuthStatus|SettlementType|AdditionalInfo1..7|ErrorStatus|ErrorDescription|Checksum
    resp_merchantid = parts[0].strip() if len(parts) > 0 else ""
    resp_customerid = parts[1].strip() if len(parts) > 1 else ""
    txn_ref = parts[2].strip() if len(parts) > 2 else ""
    bank_ref = parts[3].strip() if len(parts) > 3 else ""
    resp_amount = parts[4].strip() if len(parts) > 4 else ""
    resp_bankid = parts[5].strip() if len(parts) > 5 else ""
    resp_bankmerchantid = parts[6].strip() if len(parts) > 6 else ""
    resp_txntype = parts[7].strip() if len(parts) > 7 else ""
    resp_currencyname = parts[8].strip() if len(parts) > 8 else ""
    resp_itemcode = parts[9].strip() if len(parts) > 9 else ""
    resp_securitytype = parts[10].strip() if len(parts) > 10 else ""
    resp_securityid = parts[11].strip() if len(parts) > 11 else ""
    resp_securitypassword = parts[12].strip() if len(parts) > 12 else ""
    resp_txndate_raw = parts[13].strip() if len(parts) > 13 else ""
    auth_status = parts[14].strip() if len(parts) > 14 else ""
    resp_settlementtype = parts[15].strip() if len(parts) > 15 else ""

    resp_additional = [parts[i].strip() if len(parts) > i else "" for i in range(16, 23)]
    error_status = parts[23].strip() if len(parts) > 23 else ""
    error_desc = parts[24].strip() if len(parts) > 24 else ""

    tx = None
    if txn_ref:
        tx = PaymentBilldeskTransaction.objects.filter(utr=txn_ref).first()
        if tx is None:
            tx = PaymentBilldeskTransaction.objects.filter(transaction_id_no_hoa=txn_ref).first()

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active="Y", payment_gateway_name__iexact="Billdesk")
        .order_by("sl_no")
        .first()
    )
    encryption_key = str(getattr(gateway, "encryption_key", "") or "").strip()
    calculated_checksum = _billdesk_hmac_sha256(msg_without_checksum, encryption_key) if encryption_key else ""

    checksum_ok = bool(calculated_checksum and calculated_checksum.upper() == response_checksum.upper())
    if tx:
        try:
            parsed_amount = Decimal(str(resp_amount)).quantize(Decimal("0.01")) if resp_amount else None
        except Exception:
            parsed_amount = None

        status_code = "S" if auth_status == "0300" and checksum_ok else "F"
        tx.response_string = response_msg
        tx.response_merchantid = resp_merchantid or None
        tx.response_customerid = resp_customerid or None
        tx.response_txnreferenceno = txn_ref or None
        tx.response_bankreferenceno = bank_ref or None
        tx.response_txnamount = parsed_amount
        tx.response_bankid = resp_bankid or None
        tx.response_bankmerchantid = resp_bankmerchantid or None
        tx.response_txntype = resp_txntype or None
        tx.response_currencyname = resp_currencyname or None
        tx.response_itemcode = resp_itemcode or None
        tx.response_securitytype = resp_securitytype or None
        tx.response_securityid = resp_securityid or None
        tx.response_securitypassword = resp_securitypassword or None
        # Preserve raw string in case BillDesk changes date format.
        tx.response_txndate = None
        tx.response_authstatus = auth_status or None
        tx.response_settlementtype = resp_settlementtype or None
        tx.response_additionalinfo1 = resp_additional[0] or None
        tx.response_additionalinfo2 = resp_additional[1] or None
        tx.response_additionalinfo3 = resp_additional[2] or None
        tx.response_additionalinfo4 = resp_additional[3] or None
        tx.response_additionalinfo5 = resp_additional[4] or None
        tx.response_additionalinfo6 = resp_additional[5] or None
        tx.response_additionalinfo7 = resp_additional[6] or None
        tx.response_errorstatus = error_status or None
        tx.response_errordescription = error_desc or None
        tx.response_checksum = response_checksum or None
        tx.response_checksum_calculated = calculated_checksum or None
        tx.response_initial_authstatus = auth_status or None
        tx.response_initial_datetime = timezone.now()
        tx.payment_status = status_code
        tx.opr_date = timezone.now()
        tx.save()

    frontend_success = str(getattr(settings, "PAYMENT_GATEWAY_FRONTEND_SUCCESS_URL", "") or "").strip()
    if not frontend_success:
        return HttpResponseBadRequest("PAYMENT_GATEWAY_FRONTEND_SUCCESS_URL not configured")

    if tx:
        wallet_type = str(tx.request_additionalinfo3 or "").strip()
        hoa = str(tx.request_additionalinfo1 or "").strip()
        amt = f"{Decimal(str(tx.transaction_amount or 0)).quantize(Decimal('0.01')):.2f}"
        created_at = tx.transaction_date.isoformat() if tx.transaction_date else ""
    else:
        wallet_type = ""
        hoa = ""
        amt = resp_amount or ""
        created_at = ""

    ui_status = "success" if auth_status == "0300" and checksum_ok else "failed"
    query = urlencode(
        {
            "transactionId": txn_ref,
            "walletType": wallet_type,
            "hoa": hoa,
            "amount": amt,
            "status": ui_status,
            "createdAt": created_at,
        }
    )
    return redirect(f"{frontend_success}?{query}")
