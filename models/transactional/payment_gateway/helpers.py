from decimal import Decimal
import json
import logging
import secrets
import urllib.parse
from django.views.decorators.csrf import csrf_exempt
from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from auth.user.models import CustomUser
from auth.workflow.services import WorkflowService
from models.transactional.new_license_application.models import NewLicenseApplication
from models.transactional.wallet.wallet_service import credit_wallet_balance, record_wallet_transaction
from models.transactional.payment_gateway.epay_python_sdk.types import OrderEntity
from models.transactional.payment_gateway.sbiepay_utils import get_sbiepay_client
from models.transactional.salesman_barman.serializers import DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE
from .models import MasterPaymentModule, PaymentGatewayParameters, PaymentSBIePayTransaction, PaymentSendHOA
from models.transactional.wallet.models import _resolve_wallet_row_licensee_id
from models.transactional.wallet.models import WalletBalance

logger = logging.getLogger(__name__)


def normalize_wallet_type(wallet_type: str) -> str:
    value = str(wallet_type or "").strip().lower().replace(" ", "_").replace("-", "_")
    if value in {"education", "educationcess", "education_cess", "educationcesswallet", "education_cess_wallet"}:
        return "education_cess"
    if value in {"excise", "excise_duty", "excise_duty_wallet", "exciseduty", "excise_wallet"}:
        return "excise"
    return value


def resolve_wallet_head_of_account(*, licensee_id: str, wallet_type: str, user_id: str = "") -> str:
    """
    Resolve Head Of Account for wallet recharge initiation.

    Important: the incoming licensee_id may be a username or a NA/NLI alias used by
    different clients. Use the same resolver as wallet transaction recording to
    map it to the actual WalletBalance.licensee_id stored in DB.
    """
    lid = str(licensee_id or "").strip()
    wtype = str(wallet_type or "").strip()
    uid = str(user_id or "").strip()
    if not lid or not wtype:
        return ""
    try:
        resolved_lid = _resolve_wallet_row_licensee_id(lid, uid) or lid
        qs = (
            WalletBalance.objects.filter(
                licensee_id__iexact=resolved_lid,
                wallet_type__code__iexact=wtype,
            )
            .order_by("wallet_balance_id")
        )
        # Prefer a non-empty/non-sentinel HOA if multiple rows exist.
        row = qs.exclude(head_of_account__isnull=True).exclude(head_of_account__exact="").exclude(head_of_account__iexact="non").first()
        if not row:
            row = qs.first()
        return str(getattr(row, "head_of_account", "") or "").strip()
    except Exception:
        return ""


def _active_na_license_id_for_applicant(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    try:
        from models.masters.license.models import License

        base = License.objects.filter(applicant=user, is_active=True)
        lic = base.filter(license_id__istartswith="NA/").order_by("-issue_date", "-license_id").first()
        if lic and lic.license_id:
            return str(lic.license_id).strip()

        lic = base.filter(source_type="new_license_application").order_by("-issue_date", "-license_id").first()
        if lic and lic.license_id:
            lid = str(lic.license_id).strip()
            if lid.upper().startswith("NA/"):
                return lid
    except Exception:
        pass
    return ""

def _normalize_amount(raw_amount) -> Decimal:
    value = Decimal(str(raw_amount or "0")).quantize(Decimal("0.01"))
    if value <= 0:
        raise ValueError("amount must be greater than zero")
    return value


def validate_payment_module_code(module_code: str) -> str:
    code = str(module_code or "").strip()
    if not code:
        raise ValueError("payment_module_code is required.")

    # check sems_master_module if it exists in the DB.
    try:
        if MasterPaymentModule.objects.filter(module_code=code).exists():
            return code
    except (OperationalError, ProgrammingError):
        pass

    raise ValueError(f"Invalid payment_module_code={code}. Not found in master module table.")


def get_module_license_fee(module_code: str) -> Decimal | None:
    code = str(module_code or "").strip()
    if not code:
        return None
    try:
        module = (
            MasterPaymentModule.objects
            .only("module_code", "license_fee")
            .filter(module_code=code)
            .first()
        )
        fee = getattr(module, "license_fee", None) if module else None
        if fee in (None, ""):
            return None
        return _normalize_amount(fee)
    except Exception:
        return None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_payment_module(request, module_code: str):
    code = str(module_code or "").strip()
    if not code:
        return Response({"detail": "module_code is required."}, status=status.HTTP_400_BAD_REQUEST)

    module = MasterPaymentModule.objects.filter(module_code=code).first()
    if not module:
        return Response({"detail": f"Module not found for module_code={code}."}, status=status.HTTP_404_NOT_FOUND)

    fee = None
    try:
        raw_fee = getattr(module, "license_fee", None)
        if raw_fee not in (None, ""):
            fee = _normalize_amount(raw_fee)
    except Exception:
        fee = None

    return Response(
        {
            "module_code": str(getattr(module, "module_code", "") or "").strip(),
            "module_desc": str(getattr(module, "module_desc", "") or "").strip(),
            "license_fee": float(fee) if fee is not None else None,
        }
    )


def generate_transaction_id(prefix: str = "TXN") -> str:
    return f"{prefix}{timezone.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"


def build_full_name_from_user(user) -> str:
    if not user:
        return ""
    parts = []
    for key in ("first_name", "middle_name", "last_name"):
        value = str(getattr(user, key, "") or "").strip()
        if value:
            parts.append(value)
    full = " ".join(parts).strip()
    if full:
        return full
    # Fallbacks commonly present on custom user/profile models.
    for key in ("name", "full_name", "fullname"):
        value = str(getattr(user, key, "") or "").strip()
        if value:
            return value
    return ""


def initiate_sbiepay_core(request, transaction_id, amount, payer_id, payment_module_code, head_of_account, wallet_type, return_url):
    client = get_sbiepay_client()
    
    # Pack your specific contextual application tracking variables
    metadata = {
        "wallet_type": wallet_type,
        "head_of_account": head_of_account,
        "payment_module_code": payment_module_code
    }
    
    # 1. Instantiate the explicit base object required by the SDK
    order_payload = OrderEntity(
        currencyCode="INR",
        orderAmount=float(amount),
        orderRefNumber=transaction_id,
        returnUrl=return_url,
        otherDetails=json.dumps(metadata)
    )

    # -----------------------------------------------------------------
    # FIXED: Strip unrecognized or null parameters out of the object
    # properties so SBI ePay's JSON parser won't throw error 2002
    # -----------------------------------------------------------------
    allowed_fields = {"currencyCode", "orderAmount", "orderRefNumber", "returnUrl", "otherDetails"}
    
    # If the SDK method accepts a dictionary instead of the full object, 
    # extract only the strictly required mapped payload parameters:
    cleaned_payload_dict = {
        key: value for key, value in order_payload.__dict__.items()
        if key in allowed_fields and value is not None
    }

    # Pass the sanitized payload dictionary or cleanly overwrite properties if the 
    # create() method specifically requires the OrderEntity class type structure:
    for key in list(order_payload.__dict__.keys()):
        if key not in allowed_fields:
            delattr(order_payload, key)

    # Trigger the order generation call using the sanitized entity schema
    response = client.order.create(order_payload)

    # Safely digest dictionary or structured custom class object data variations
    response_status = response.get("status") if isinstance(response, dict) else getattr(response, "status", None)
    response_data = response.get("data") if isinstance(response, dict) else getattr(response, "data", None)

    if response_status in (1, "1", "SUCCESS") and response_data:
        order_data = response_data[0] if isinstance(response_data, list) else response_data
        
        PaymentSBIePayTransaction.objects.update_or_create(
            order_ref_number=transaction_id,
            defaults={
                "sbi_order_ref_number": order_data.get("sbiOrderRefNumber"),
                "payer_id": payer_id,
                "payment_module_code": payment_module_code,
                "transaction_amount": amount,
                "head_of_account": head_of_account,
                "wallet_type": wallet_type,
                "transaction_url": order_data.get("transactionUrl"),
                "request_payload": json.dumps(cleaned_payload_dict),
                "payment_status": "P",
                "user_id": str(getattr(request.user, "username", "") or "").strip()[:50],
                "opr_date": timezone.now()
            }
        )

        # Retain internal cross-department accounting visibility side effects
        requisition_no = "NA"
        try:
            from .views import _active_na_license_id_for_applicant
            requisition_no = (_active_na_license_id_for_applicant(request.user) or "NA")[:50]
        except Exception:
            pass
            
        if payment_module_code == "001":  # DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE
            requisition_no = (payer_id or "NA")[:50]

        PaymentSendHOA.objects.update_or_create(
            transaction_id_no=transaction_id,
            head_of_account=head_of_account,
            defaults={
                "licensee_id": payer_id or None,
                "amount": amount,
                "payment_module_code": payment_module_code,
                "requisition_no": requisition_no,
                "opr_date": timezone.now(),
            },
        )
        return True, order_data
        
    errors = response.get("errors") if isinstance(response, dict) else getattr(response, "errors", "Unknown Gateway Error")
    return False, errors


from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest

def _process_sbiepay_transaction(encrypted_payload: str) -> bool:
    client = get_sbiepay_client()
    try:
        # Decrypt callback string payload
        decrypted_output = client.crypto.decodeCallback(encrypted_payload)
        
        if isinstance(decrypted_output, (list, dict)):
            raw_data = decrypted_output
        else:
            raw_data = json.loads(decrypted_output)
            
        # The SDK returns a list containing the transaction blocks: [{ ... }]
        if isinstance(raw_data, list) and len(raw_data) > 0:
            resp_data = raw_data[0]
        elif isinstance(raw_data, dict):
            resp_data = raw_data
        else:
            logger.error("SBIePay decrypted callback output format is unrecognized.")
            return False
            
    except Exception as e:
        logger.error(f"Failed to process or parse SBIePay callback payload: {e}")
        return False


    order_info = resp_data.get("orderInfo", {})
    payment_info = resp_data.get("paymentInfo", {})

    txn_ref = order_info.get("orderRefNumber")
    order_status = str(order_info.get("orderStatus") or "").upper()
    amount_str = order_info.get("orderAmount") or payment_info.get("orderAmount")

    if not txn_ref:
        logger.error("Missing orderRefNumber parameter identifier in callback data dictionary.")
        return False

    tx = PaymentSBIePayTransaction.objects.filter(order_ref_number=txn_ref).first()
    if not tx:
        logger.error(f"SBIePay Transaction reference {txn_ref} not found in database records.")
        return False

    if tx.payment_status == "S":
        return True  # Idempotency check: Already processed successfully

    # SBI ePay sends 'SUCCESS' or 'FAILED'
    status_code = "S" if order_status == "SUCCESS" else "F"
    
    try:
        parsed_amount = Decimal(str(amount_str)).quantize(Decimal("0.01")) if amount_str else tx.transaction_amount
    except Exception:
        parsed_amount = tx.transaction_amount

    # Save transaction state updates using exact inner fields
    tx.sbi_order_ref_number = order_info.get("sbiOrderRefNumber")
    tx.atrn = payment_info.get("atrnNumber")
    tx.payment_status = status_code
    tx.transaction_status = payment_info.get("transactionStatus") or order_status
    tx.pay_mode = payment_info.get("payMode")
    tx.bank_ref_number = payment_info.get("bankTxnNumber")
    tx.bank_name = payment_info.get("bankName")
    tx.response_payload = json.dumps(resp_data)
    tx.opr_date = timezone.now()
    tx.save()

    module_code = str(tx.payment_module_code or "").strip()

    if module_code == DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE:
        if status_code == "S":
            try:                 
                application_id = str(tx.payer_id or "").strip()
                app = NewLicenseApplication.objects.select_related("workflow", "current_stage", "applicant").filter(application_id__iexact=application_id).first()
                if app:
                    if not getattr(app, "is_application_fee_paid", False):
                        app.is_application_fee_paid = True
                        app.save(update_fields=["is_application_fee_paid"])

                    stage = getattr(app, "current_stage", None)
                    stage_name = str(getattr(stage, "name", "") or "").strip().lower()
                    if ("reject" in stage_name or getattr(stage, "is_final", False)) and getattr(app, "workflow", None):
                        initial = app.workflow.stages.filter(is_initial=True).order_by("id").first()
                        if initial and getattr(app, "current_stage_id", None) != getattr(initial, "id", None):
                            app.current_stage = initial
                            app.save(update_fields=["current_stage"])

                    username = str(tx.user_id or "").strip()
                    user = CustomUser.objects.filter(username__iexact=username).first() if username else getattr(app, "applicant", None)
                    if getattr(getattr(app, "current_stage", None), "is_initial", False):
                        WorkflowService.submit_application(application=app, user=user, remarks="Application fee paid via SBIePay (auto-submitted)")

                    if getattr(app, "mode_of_operation", None) in {"Salesman", "Barman"}:
                        from models.transactional.salesman_barman.models import SalesmanBarmanModel
                        from auth.workflow.constants import WORKFLOW_IDS
                        from auth.workflow.models import WorkflowStage, Workflow
                        from django.db import transaction as db_transaction

                        wf = Workflow.objects.filter(id=WORKFLOW_IDS.get("SALESMAN_BARMAN")).first()
                        if wf:
                            init = WorkflowStage.objects.filter(workflow=wf, is_initial=True).order_by("id").first()
                            if init:
                                sb = SalesmanBarmanModel.objects.filter(new_license_application=app).first()
                                if not sb:
                                    sb = SalesmanBarmanModel(workflow=wf, current_stage=init, new_license_application=app, excise_district=getattr(app, "site_district", None), license_category=getattr(app, "license_category", None), applicant=user, role=getattr(app, "mode_of_operation", None))
                                else:
                                    sb.workflow = wf
                                    sb.current_stage = init
                                    sb.applicant = user or sb.applicant
                                with db_transaction.atomic():
                                    sb.save()
                                sb.refresh_from_db()
                                if getattr(getattr(sb, "current_stage", None), "is_initial", False):
                                    WorkflowService.submit_application(application=sb, user=user, remarks="Auto-submitted with New License")
            except Exception as exc:
                logger.exception("Failed to execute auto-submit workflow routines: %s", exc)
        elif status_code == "F":
            try:
                app = NewLicenseApplication.objects.only("application_id", "is_application_fee_paid").filter(application_id__iexact=tx.payer_id).first()
                if app and getattr(app, "is_application_fee_paid", False):
                    app.is_application_fee_paid = False
                    app.save(update_fields=["is_application_fee_paid"])
            except Exception as exc:
                logger.exception("Failed to preserve unpaid state structure: %s", exc)
    else:
        # Wallet recharge processing pipeline
        if status_code == "S":
            try:
                credit_wallet_balance(
                    transaction_id=txn_ref, licensee_id=tx.payer_id, wallet_type=tx.wallet_type,
                    head_of_account=tx.head_of_account, amount=parsed_amount, user_id=tx.user_id,
                    source_module="wallet_recharge", transaction_type="recharge", remarks="SBIePay success"
                )
                if tx.wallet_type == "security_deposit":
                    from django.db.models import Q
                    from models.masters.license.models import License
                    from models.transactional.new_license_application.payment_status import sync_new_license_payment_status
                    from models.transactional.wallet.views import _wallet_license_candidates

                    candidates = _wallet_license_candidates(tx.payer_id)
                    lic = License.objects.filter(license_id__in=candidates).order_by("-issue_date", "-license_id").first()
                    application = NewLicenseApplication.objects.filter(application_id=lic.source_object_id).first() if lic and lic.source_type == "new_license_application" else None

                    if not application or getattr(application, "is_approved", False) or getattr(application, "is_security_fee_paid", False):
                        user = CustomUser.objects.filter(username__iexact=tx.user_id).first() or getattr(lic, "applicant", None)
                        if user:
                            application = NewLicenseApplication.objects.filter(applicant=user, is_approved=False, is_security_fee_paid=False).first()

                    if application and not application.is_security_fee_paid:
                        application.is_security_fee_paid = True
                        application.save(update_fields=["is_security_fee_paid"])
                        sync_new_license_payment_status(application)
            except Exception as exc:
                logger.exception("Failed to credit wallet: %s", exc)
        elif status_code == "F":
            try:
                record_wallet_transaction(
                    transaction_id=txn_ref, licensee_id=tx.payer_id, wallet_type=tx.wallet_type,
                    head_of_account=tx.head_of_account, amount=parsed_amount, user_id=tx.user_id,
                    source_module="wallet_recharge", transaction_type="recharge", payment_status="failed", remarks=f"SBIePay payment failed"
                )
            except Exception as exc:
                logger.exception("Failed to log failed wallet txn: %s", exc)

    return True


@csrf_exempt
def sbiepay_response(request):
    if request.method not in ("GET", "POST"):
        return HttpResponseBadRequest("Invalid request method layout")

    data_pool = request.GET if request.method == "GET" else request.POST
    encrypted_data = data_pool.get("encryptedPaymentFinalResponse") or data_pool.get("encData")

    # This variables will hold extracted inner payload blocks to send to the frontend string
    txn_ref = "N/A"
    sbi_ref = ""
    order_status = "PENDING"
    amount_str = "0"
    wallet_type = ""
    hoa = ""

    if encrypted_data:
        sanitized_data = str(encrypted_data).strip().replace(" ", "+")
        missing_padding = len(sanitized_data) % 4
        if missing_padding:
            sanitized_data += "=" * (4 - missing_padding)
            
        # Execute processing logic
        client = get_sbiepay_client()
        try:
            decrypted_output = client.crypto.decodeCallback(sanitized_data)
            if isinstance(decrypted_output, (list, dict)):
                raw_data = decrypted_output
            else:
                raw_data = json.loads(decrypted_output)
                
            if isinstance(raw_data, list) and len(raw_data) > 0:
                resp_data = raw_data[0]
            else:
                resp_data = raw_data
                
            order_info = resp_data.get("orderInfo", {})
            payment_info = resp_data.get("paymentInfo", {})

            txn_ref = order_info.get("orderRefNumber", "N/A")
            sbi_ref = order_info.get("sbiOrderRefNumber", "")
            order_status = str(order_info.get("orderStatus") or "PENDING").upper()
            amount_str = str(order_info.get("orderAmount") or payment_info.get("orderAmount") or "0")
            
            # Retrieve original context fields from database transaction to forward to frontend
            tx = PaymentSBIePayTransaction.objects.filter(order_ref_number=txn_ref).first()
            if tx:
                wallet_type = tx.wallet_type or ""
                hoa = tx.head_of_account or ""
                
            # Process side effects safely inside the original function
            _process_sbiepay_transaction(sanitized_data)
            
        except Exception as e:
            logger.error(f"Redirection parameter packing parsing exception: {e}")

    # Fetch active gateway mapping configuration
    gateway = PaymentGatewayParameters.objects.filter(is_active=True, payment_gateway_name__iexact="SBIePay").first()
    base_redirect_url = getattr(gateway, "frontend_success_url", "/") or "/"

    # -----------------------------------------------------------------
    # FIXED: Build explicit query string parameters to forward to Angular
    # -----------------------------------------------------------------
    query_params = {
        "orderRefNumber": txn_ref,
        "sbiOrderRefNumber": sbi_ref,
        "walletType": wallet_type,
        "hoa": hoa,
        "orderAmount": amount_str,
        "orderStatus": order_status.lower(), # Standardized lowercase format
        "createdAt": timezone.now().isoformat()
    }
    
    # URL encode parameters cleanly to handle spaces/symbols safely across routes
    url_parts = list(urllib.parse.urlparse(base_redirect_url))
    existing_queries = urllib.parse.parse_qsl(url_parts[4])
    existing_queries.extend(query_params.items())
    url_parts[4] = urllib.parse.urlencode(existing_queries)
    
    final_forwarded_url = urllib.parse.urlunparse(url_parts)

    # Use the compiled final URL containing your dynamic text inside your popup handler script
    dynamic_html = f"""
    <!DOCTYPE html>
    <html>
        <head><title>Processing Payment Response...</title></head>
        <body>
            <h3 style="text-align:center; font-family:sans-serif; margin-top:20px;">
                Payment Processed Successfully. Redirecting...
            </h3>
            <script>
                var targetUrl = "{final_forwarded_url}";
                try {{
                    if (window.opener && !window.opener.closed) {{
                        window.opener.location.href = targetUrl;
                    }}
                }} catch (e) {{
                    console.warn("Parent redirection routing mapping exception:", e);
                }}
                window.close();
                setTimeout(function() {{
                    if (!window.closed) {{ window.location.href = targetUrl; }}
                }}, 500);
            </script>
        </body>
    </html>
    """
    return HttpResponse(dynamic_html, content_type="text/html")