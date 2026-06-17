import logging
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from models.transactional.wallet.wallet_service import record_wallet_transaction
from models.transactional.new_license_application.models import NewLicenseApplication
from auth.user.models import CustomUser
from .models import PaymentGatewayParameters, MasterPaymentModule, PaymentSBIePayTransaction
from .helpers import build_full_name_from_user, get_module_license_fee, resolve_wallet_head_of_account, normalize_wallet_type, _active_na_license_id_for_applicant, generate_transaction_id, _normalize_amount, initiate_sbiepay_core, validate_payment_module_code

logger = logging.getLogger(__name__)

LICENSE_FEE_HOA = "0039-00-800-45-02"
SECURITY_DEPOSIT_HOA_SENTINEL = "non"
DEFAULT_LICENSE_RENEWAL_MODULE_CODE = "002"
DEFAULT_WALLET_ADVANCE_MODULE_CODE = "999"
DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE = "001"
PENDING_RETRY_LOCK_MINUTES = 1


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sbiepay_initiate_wallet_recharge(request):
    data = request.data or {}
    transaction_id = str(data.get("transaction_id") or "").strip() or generate_transaction_id("SIKPAY")
    wallet_type = normalize_wallet_type(data.get("wallet_type"))
    licensee_id = str(data.get("licensee_id") or data.get("licenseeId") or "").strip()[:50]
    head_of_account = str(data.get("head_of_account") or "").strip()
    payment_module_code = str(data.get("payment_module_code") or DEFAULT_WALLET_ADVANCE_MODULE_CODE).strip()
    payer_id = str(data.get("payer_id") or getattr(request.user, "username", "") or "").strip()[:50]
    raw_amount = data.get("amount")

    if not licensee_id:
        licensee_id = str(_active_na_license_id_for_applicant(request.user) or "").strip()[:50]

    resolved_hoa = resolve_wallet_head_of_account(licensee_id=licensee_id, wallet_type=wallet_type, user_id=str(getattr(request.user, "username", "") or "").strip())
    if resolved_hoa: head_of_account = resolved_hoa

    try:
        amount = _normalize_amount(raw_amount)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    gateway = PaymentGatewayParameters.objects.filter(is_active=True, payment_gateway_name__iexact="SBIePay").first()
    return_url = str(gateway.return_url if gateway and gateway.return_url else request.build_absolute_uri(reverse("payment_gateway:sbiepay-response")))

    success, result = initiate_sbiepay_core(request, transaction_id, amount, payer_id, payment_module_code, head_of_account, wallet_type, return_url)

    if not success:
        return Response({"detail": "Gateway Error", "error": str(result)}, status=status.HTTP_502_BAD_GATEWAY)

    # Preserve Wallet Transaction log
    try:
        record_wallet_transaction(
            transaction_id=transaction_id, licensee_id=payer_id, wallet_type=wallet_type,
            head_of_account=head_of_account, amount=amount, entry_type="CR", transaction_type="recharge",
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            source_module="wallet_recharge", payment_status="pending", remarks="SBIePay payment initiated",
        )
    except Exception as exc:
        logger.warning("Failed to record pending wallet transaction: %s", exc)

    return Response({
        "success": True,
        "transaction_id": transaction_id,
        "transactionUrl": result.get("transactionUrl") 
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sbiepay_initiate_license_fee(request):
    data = request.data or {}

    transaction_id = str(data.get("transaction_id") or "").strip() or generate_transaction_id("SIKPAY")
    payer_id = str(data.get("payer_id") or data.get("licensee_id") or "").strip()[:50]
    payment_module_code = str(data.get("payment_module_code") or "").strip() or DEFAULT_LICENSE_RENEWAL_MODULE_CODE
    raw_amount = data.get("amount")

    if not payer_id:
        return Response({"detail": "licensee id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        payment_module_code = validate_payment_module_code(payment_module_code)
    except Exception as exc:
        logger.warning(
            "Invalid payment_module_code=%s for license fee initiation; proceeding with raw value. err=%s",
            payment_module_code, exc
        )

    try:
        amount = _normalize_amount(raw_amount)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    gateway = PaymentGatewayParameters.objects.filter(is_active=True, payment_gateway_name__iexact="SBIePay").first()
    return_url = str(gateway.return_url if gateway and gateway.return_url else request.build_absolute_uri(reverse("payment_gateway:sbiepay-response")))

    # 1. Call core SBIePay initiation
    success, result = initiate_sbiepay_core(
        request, transaction_id, amount, payer_id, payment_module_code, 
        LICENSE_FEE_HOA, "license_fee", return_url
    )

    if not success:
        return Response({"detail": "Gateway Error", "error": str(result)}, status=status.HTTP_502_BAD_GATEWAY)

    # 2. Preserve wallet logging
    try:
        record_wallet_transaction(
            transaction_id=transaction_id,
            licensee_id=payer_id,
            wallet_type="license_fee",
            head_of_account=LICENSE_FEE_HOA,
            amount=amount,
            entry_type="CR",
            transaction_type="recharge",
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            source_module="wallet_recharge",
            payment_status="pending",
            remarks="SBIePay payment initiated",
        )
    except Exception as exc:
        logger.warning("Failed to record pending license fee transaction for txn_id=%s: %s", transaction_id, exc)

    return Response({
        "success": True,
        "transaction_id": transaction_id,
        "transactionUrl": result.get("transactionUrl")
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sbiepay_initiate_security_deposit(request):
    data = request.data or {}

    transaction_id = str(data.get("transaction_id") or "").strip() or generate_transaction_id("SIKFDR")
    payer_id = str(data.get("payer_id") or data.get("licensee_id") or "").strip()[:50]
    licensee_name = str(data.get("licensee_name") or "").strip()
    account_holder_name = str(data.get("account_holder_name") or data.get("full_name") or data.get("customer_name") or "").strip()
    payment_module_code = str(data.get("payment_module_code") or "").strip() or DEFAULT_LICENSE_RENEWAL_MODULE_CODE
    raw_amount = data.get("amount")

    if not payer_id:
        return Response({"detail": "licensee id is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not account_holder_name:
        account_holder_name = build_full_name_from_user(getattr(request, "user", None))
    if not account_holder_name:
        account_holder_name = licensee_name or payer_id
    if not licensee_name:
        licensee_name = account_holder_name or payer_id

    try:
        payment_module_code = validate_payment_module_code(payment_module_code)
    except Exception as exc:
        logger.warning(
            "Invalid payment_module_code=%s for security deposit initiation; proceeding with raw value. err=%s",
            payment_module_code, exc
        )

    try:
        amount = _normalize_amount(raw_amount)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    gateway = PaymentGatewayParameters.objects.filter(is_active=True, payment_gateway_name__iexact="SBIePay").first()
    return_url = str(gateway.return_url if gateway and gateway.return_url else request.build_absolute_uri(reverse("payment_gateway:sbiepay-response")))

    # 1. Call core SBIePay initiation
    success, result = initiate_sbiepay_core(
        request, transaction_id, amount, payer_id, payment_module_code, 
        SECURITY_DEPOSIT_HOA_SENTINEL, "security_deposit", return_url
    )

    if not success:
        return Response({"detail": "Gateway Error", "error": str(result)}, status=status.HTTP_502_BAD_GATEWAY)

    # 2. Preserve wallet logging
    try:
        record_wallet_transaction(
            transaction_id=transaction_id,
            licensee_id=payer_id,
            licensee_name=licensee_name,
            wallet_type="security_deposit",
            head_of_account=SECURITY_DEPOSIT_HOA_SENTINEL,
            amount=amount,
            entry_type="CR",
            transaction_type="recharge",
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            source_module="wallet_recharge",
            payment_status="pending",
            remarks="SBIePay payment initiated",
        )
    except Exception as exc:
        logger.warning("Failed to record pending security deposit transaction for txn_id=%s: %s", transaction_id, exc)

    return Response({
        "success": True,
        "transaction_id": transaction_id,
        "transactionUrl": result.get("transactionUrl")
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sbiepay_initiate_new_license_application_fee(request):
    data = request.data or {}
    application_id = str(data.get("application_id") or data.get("payer_id") or "").strip()[:50]
    
    if not application_id:
        return Response({"detail": "application_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    transaction_id = str(data.get("transaction_id") or "").strip() or generate_transaction_id("NLIAPP")
    raw_amount = data.get("amount")
    payment_module_code = str(data.get("payment_module_code") or "").strip() or DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE
    head_of_account = str(data.get("head_of_account") or LICENSE_FEE_HOA).strip() or LICENSE_FEE_HOA

    try:
        payment_module_code = validate_payment_module_code(payment_module_code)
    except Exception as exc:
        logger.warning(
            "Invalid payment_module_code=%s for new license application fee; proceeding with raw value. err=%s",
            payment_module_code, exc
        )

    try:
        module_fee = get_module_license_fee(payment_module_code)
        if module_fee is None:
            return Response(
                {"detail": f"license_fee is not configured for payment_module_code={payment_module_code}.", "payment_module_code": payment_module_code},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Ensure frontend amount matches DB amount
        if raw_amount not in (None, ""):
            client_amount = _normalize_amount(raw_amount)
            if client_amount != module_fee:
                return Response(
                    {"detail": "Invalid amount. Please refresh and try again.", "expected_amount": float(module_fee), "received_amount": float(client_amount)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        amount = module_fee
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    gateway = PaymentGatewayParameters.objects.filter(is_active=True, payment_gateway_name__iexact="SBIePay").first()
    return_url = str(gateway.return_url if gateway and gateway.return_url else request.build_absolute_uri(reverse("payment_gateway:sbiepay-response")))

    # 1. Call core SBIePay initiation (Passing 'application_fee' as a placeholder wallet_type)
    success, result = initiate_sbiepay_core(
        request, transaction_id, amount, application_id, payment_module_code, 
        head_of_account, "application_fee", return_url
    )

    if not success:
        return Response({"detail": "Gateway Error", "error": str(result)}, status=status.HTTP_502_BAD_GATEWAY)

    # Note: New License App Fee intentionally doesn't log a pending `wallet_transaction` here
    # according to your original BillDesk code.

    return Response({
        "success": True,
        "transaction_id": transaction_id,
        "application_id": application_id,
        "transactionUrl": result.get("transactionUrl")
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_billdesk_transactions(request):
    from django.db.models import Q
    
    # Authorization check: only allow roleId 1 (Site Admin) or roleId 3 (Single Window)
    role_id = getattr(getattr(request.user, 'role', None), 'id', None)
    if role_id not in (1, 3):
        return Response({"detail": "Permission denied. Admin/Single Window only."}, status=status.HTTP_403_FORBIDDEN)

    queryset = PaymentSBIePayTransaction.objects.all()

    # Filters
    query = request.query_params.get("query", "").strip()
    status_filter = request.query_params.get("status", "").strip()
    
    if status_filter:
        queryset = queryset.filter(payment_status__iexact=status_filter)

    if query:
        # Check if amount query
        amount_query = None
        try:
            amount_query = float(query)
        except ValueError:
            pass

        q_obj = Q(utr__icontains=query) | Q(transaction_id_no_hoa__icontains=query) | Q(payer_id__icontains=query) | Q(user_id__icontains=query)
        if amount_query is not None:
            q_obj |= Q(transaction_amount=amount_query)
        queryset = queryset.filter(q_obj)

    queryset = queryset.order_by('-transaction_date')

    # Pagination parameters
    try:
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 10))
    except (ValueError, TypeError):
        page = 1
        page_size = 10

    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    total_count = queryset.count()
    offset = (page - 1) * page_size
    items = queryset[offset: offset + page_size]

    # Resolve applicant names helper
    def get_user_display_name(u):
        if not u:
            return "N/A"
        name = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip()
        return name or getattr(u, "username", None) or "N/A"

    def resolve_name(reference):
        ref = str(reference or "").strip()
        if not ref:
            return "N/A"
        try:
            # Try NewLicenseApplication
            app = NewLicenseApplication.objects.select_related("applicant").filter(application_id__iexact=ref).first()
            if app:
                return get_user_display_name(app.applicant)

            # Try RenewalApplication
            from models.transactional.license_renewal_application.models import LicenseApplication as RenewalApplication
            renewal = RenewalApplication.objects.select_related("applicant").filter(application_id__iexact=ref).first()
            if renewal:
                return get_user_display_name(renewal.applicant)

            # Try SalesmanBarmanModel
            from models.transactional.salesman_barman.models import SalesmanBarmanModel
            staff = SalesmanBarmanModel.objects.filter(application_id__iexact=ref).first()
            if staff:
                return f"{staff.firstName or ''} {staff.lastName or ''}".strip() or get_user_display_name(staff.applicant)

            # Try License
            from models.masters.license.models import License
            license_obj = License.objects.select_related("applicant").filter(license_id__iexact=ref).first()
            if license_obj:
                return get_user_display_name(license_obj.applicant)

            # Try direct user match
            user_filter = Q(username__iexact=ref)
            if ref.isdigit():
                user_filter |= Q(id=int(ref))
            user = CustomUser.objects.filter(user_filter).first()
            return get_user_display_name(user) if user else "N/A"
        except Exception:
            return "N/A"

    serialized_data = []
    for tx in items:
        # Resolve module code description
        purpose = "Application Fee"
        if tx.payment_module_code == "002":
            purpose = "Renewal Fee"
        elif tx.payment_module_code == "999":
            purpose = "Wallet Recharge"
        else:
            try:
                mod = MasterPaymentModule.objects.filter(module_code=tx.payment_module_code).first()
                if mod and mod.module_desc:
                    purpose = mod.module_desc
            except Exception:
                pass

        # Resolve applicant name
        applicant_name = resolve_name(tx.payer_id)
        if applicant_name == "N/A" and tx.user_id:
            applicant_name = resolve_name(tx.user_id)

        serialized_data.append({
            "utr": tx.utr,
            "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
            "transaction_id_no_hoa": tx.transaction_id_no_hoa,
            "payer_id": tx.payer_id,
            "payment_module_code": tx.payment_module_code,
            "purpose": purpose,
            "transaction_amount": str(tx.transaction_amount),
            "payment_status": tx.payment_status,
            "user_id": tx.user_id,
            "applicant_name": applicant_name,
            "response_bankreferenceno": tx.response_bankreferenceno,
            "response_txndate": tx.response_txndate.isoformat() if tx.response_txndate else None,
            "response_errordescription": tx.response_errordescription,
            "response_authstatus": tx.response_authstatus,
        })

    return Response({
        'count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': (total_count + page_size - 1) // page_size,
        'results': serialized_data,
    })

