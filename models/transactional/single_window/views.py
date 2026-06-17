from django.db.models import Q, Value
from django.db.models.functions import Concat, Coalesce
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes, renderer_classes
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from auth.user.models import CustomUser
from models.masters.license.models import License
from models.transactional.new_license_application.models import NewLicenseApplication
from models.transactional.license_renewal_application.models import LicenseApplication as RenewalApplication
from models.transactional.salesman_barman.models import SalesmanBarmanModel


def get_current_run_start_time(content_type, object_id):
    try:
        from auth.workflow.models import Transaction
        txs = Transaction.objects.filter(content_type=content_type, object_id=str(object_id)).order_by("timestamp")
        start_time = None
        for tx in txs:
            stage_name = tx.stage.name.lower() if tx.stage else ""
            remarks = (tx.remarks or "").lower()
            if "applied" in stage_name or "submitted" in remarks:
                start_time = tx.timestamp
        return start_time
    except Exception:
        return None


def serialize_workflow_history(obj):
    hist = []
    try:
        from django.contrib.contenttypes.models import ContentType
        from auth.workflow.models import Transaction
        ct = ContentType.objects.get_for_model(obj)
        txs = list(Transaction.objects.filter(content_type=ct, object_id=str(obj.pk)).order_by("timestamp"))
        
        # Find index of latest Applied transaction to show only current run's flow
        start_idx = 0
        for i, tx in enumerate(txs):
            stage_name = tx.stage.name.lower() if tx.stage else ""
            remarks = (tx.remarks or "").lower()
            if "applied" in stage_name or "submitted" in remarks:
                start_idx = i
        
        txs = txs[start_idx:]
        for tx in txs:
            stage_name = tx.stage.name if tx.stage else "N/A"
            performed_by = tx.performed_by
            actor_username = performed_by.username if performed_by else "System"
            actor_name = f"{performed_by.first_name} {performed_by.last_name}".strip() if performed_by else "System"
            forwarded_to_name = tx.forwarded_to.name if tx.forwarded_to else "N/A"
            hist.append({
                "stage": stage_name,
                "forwarded_to": forwarded_to_name,
                "action_by": actor_username,
                "action_by_name": actor_name,
                "remarks": tx.remarks or "No remarks provided.",
                "created_at": tx.timestamp.strftime("%Y-%m-%d %H:%M:%S") if tx.timestamp else "N/A"
            })
    except Exception as e:
        pass
    return hist


def serialize_objections(obj):
    objs = []
    try:
        from django.contrib.contenttypes.models import ContentType
        from auth.workflow.models import Objection
        ct = ContentType.objects.get_for_model(obj)
        
        start_time = get_current_run_start_time(ct, obj.pk)
        objections = Objection.objects.filter(content_type=ct, object_id=str(obj.pk))
        if start_time:
            objections = objections.filter(raised_on__gte=start_time)
        objections = objections.order_by("-raised_on")
        for ob in objections:
            raised_by = ob.raised_by
            objs.append({
                "objection_remarks": ob.remarks or "",
                "objection_by": raised_by.username if raised_by else "System",
                "objection_by_name": f"{raised_by.first_name} {raised_by.last_name}".strip() if raised_by else "System",
                "stage": ob.stage.name if ob.stage else "N/A",
                "reply_remarks": ob.after_content or "No reply submitted yet.",
                "is_resolved": ob.is_resolved,
                "created_at": ob.raised_on.strftime("%Y-%m-%d %H:%M:%S") if ob.raised_on else "N/A"
            })
    except Exception as e:
        pass
    return objs


def serialize_payment_transactions(app_id):
    payments = []
    if not app_id:
        return payments
        
    try:
        from models.transactional.payment_gateway.models import PaymentBilldeskTransaction
        from models.transactional.wallet.models import WalletTransaction
        
        # 1. Query Billdesk Transactions
        bd_txs = PaymentBilldeskTransaction.objects.filter(payer_id__iexact=app_id).order_by("-transaction_date")
        for tx in bd_txs:
            status_map = {"S": "Success", "F": "Failed", "P": "Pending"}
            status = status_map.get(tx.payment_status, "Pending")
            
            purpose = "Application Fee"
            if tx.payment_module_code == "002":
                purpose = "Renewal Fee"
            elif tx.payment_module_code == "999":
                purpose = "Wallet Recharge"
            
            desc = tx.response_errordescription or f"BillDesk payment for {purpose}"
            if tx.response_errorstatus:
                desc = f"BillDesk payment for {purpose} - Failed (Error: {tx.response_errordescription or tx.response_errorstatus})"
            elif status == "Success":
                desc = f"BillDesk payment for {purpose} - Successful"
                
            payments.append({
                "transaction_id": tx.utr or tx.transaction_id_no_hoa or "N/A",
                "amount": str(tx.transaction_amount),
                "payment_type": "BillDesk Gateway",
                "payment_status": status,
                "created_at": tx.transaction_date.strftime("%Y-%m-%d %H:%M:%S") if tx.transaction_date else "N/A",
                "remarks": desc
            })
            
        # 2. Query Wallet Transactions
        wallet_txs = WalletTransaction.objects.filter(reference_no__iexact=app_id).order_by("-created_at")
        for tx in wallet_txs:
            status = "Success"
            if tx.payment_status.lower() == "failed":
                status = "Failed"
            elif tx.payment_status.lower() in ("pending", "p"):
                status = "Pending"
                
            display_txn_id = tx.transaction_id
            if display_txn_id and not str(display_txn_id).startswith("BILLDESK") and len(display_txn_id) == 24:
                from datetime import timedelta
                time_margin = timedelta(hours=2)
                candidates = [c for c in [str(tx.user_id).strip(), str(tx.licensee_id).strip()] if c]
                bd_match = PaymentBilldeskTransaction.objects.filter(
                    payer_id__in=candidates,
                    payment_status="S",
                    transaction_amount=tx.amount,
                    transaction_date__gte=tx.created_at - time_margin,
                    transaction_date__lte=tx.created_at + time_margin
                ).order_by("-transaction_date").first()
                if bd_match:
                    display_txn_id = bd_match.utr
                    
            payments.append({
                "transaction_id": display_txn_id or "N/A",
                "amount": str(tx.amount),
                "payment_type": "Wallet Balance",
                "payment_status": status,
                "created_at": tx.created_at.strftime("%Y-%m-%d %H:%M:%S") if tx.created_at else "N/A",
                "remarks": tx.remarks or f"Wallet {tx.transaction_type} ({tx.entry_type})"
            })
            
    except Exception as e:
        pass
        
    payments.sort(key=lambda x: x["created_at"], reverse=True)
    return payments




@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@permission_classes([IsAuthenticated])
def single_window_search(request):
    query = request.query_params.get("query", "").strip()
    if not query:
        return Response({"results": []})

    search_type = request.query_params.get("search_type", "registry").strip().lower()

    # Extract optional advanced filters
    day = request.query_params.get("day", "").strip()
    month = request.query_params.get("month", "").strip()
    year = request.query_params.get("year", "").strip()
    category = request.query_params.get("category", "").strip()
    role = request.query_params.get("role", "").strip()

    day_val = int(day) if day.isdigit() else None
    month_val = int(month) if month.isdigit() else None
    year_val = int(year) if year.isdigit() else None

    def apply_date_filters(qs, date_field):
        if day_val:
            qs = qs.filter(**{f"{date_field}__day": day_val})
        if month_val:
            qs = qs.filter(**{f"{date_field}__month": month_val})
        if year_val:
            qs = qs.filter(**{f"{date_field}__year": year_val})
        return qs

    def apply_category_filter(qs, cat_field):
        if category:
            return qs.filter(**{f"{cat_field}__icontains": category})
        return qs

    def apply_role_filter(qs, role_field):
        if role:
            return qs.filter(**{f"{role_field}__icontains": role})
        return qs

    def get_user_display_name(user):
        if not user:
            return "N/A"
        name = f"{getattr(user, 'first_name', '') or ''} {getattr(user, 'last_name', '') or ''}".strip()
        return name or getattr(user, "username", None) or "N/A"

    def resolve_applicant_name(reference):
        ref = str(reference or "").strip()
        if not ref:
            return "N/A"

        try:
            app = NewLicenseApplication.objects.select_related("applicant").filter(application_id__iexact=ref).first()
            if app:
                return get_user_display_name(app.applicant)

            renewal = RenewalApplication.objects.select_related("applicant").filter(application_id__iexact=ref).first()
            if renewal:
                return get_user_display_name(renewal.applicant)

            staff = SalesmanBarmanModel.objects.filter(application_id__iexact=ref).first()
            if staff:
                return f"{staff.firstName or ''} {staff.lastName or ''}".strip() or get_user_display_name(staff.applicant)

            license_obj = License.objects.select_related("applicant").filter(license_id__iexact=ref).first()
            if license_obj:
                return get_user_display_name(license_obj.applicant)

            user_filter = Q(username__iexact=ref)
            if ref.isdigit():
                user_filter |= Q(id=int(ref))
            user = CustomUser.objects.filter(user_filter).first()
            return get_user_display_name(user) if user else "N/A"
        except Exception:
            return "N/A"

    def resolve_payment_target_info(payer_id_or_ref):
        ref = str(payer_id_or_ref or "").strip()
        if not ref:
            return None, None, None

        ref_upper = ref.upper()
        try:
            from auth.user.models import CustomUser
            from models.masters.license.models import License
            from models.transactional.new_license_application.models import NewLicenseApplication
            from models.transactional.license_renewal_application.models import LicenseApplication as RenewalApplication
            from models.transactional.salesman_barman.models import SalesmanBarmanModel

            # 1. Check if it matches an application prefix
            if ref_upper.startswith(("NLA/", "NA/", "NLI/")):
                app = NewLicenseApplication.objects.filter(application_id__iexact=ref).first()
                if app:
                    user_id = app.applicant_id if app.applicant else None
                    return "new_license_app", app.application_id, user_id
            
            elif ref_upper.startswith(("LRA/", "LA/")):
                renewal = RenewalApplication.objects.filter(application_id__iexact=ref).first()
                if renewal:
                    user_id = renewal.applicant_id if renewal.applicant else None
                    return "renewal_app", renewal.application_id, user_id

            elif ref_upper.startswith(("SBM/", "SB/", "RSBM/")):
                sbm = SalesmanBarmanModel.objects.filter(application_id__iexact=ref).first()
                if sbm:
                    user_id = sbm.applicant_id if sbm.applicant else None
                    return "salesman_barman_app", sbm.application_id, user_id

            # 2. Check if there is a CustomUser matching username or id
            user_filter = Q(username__iexact=ref)
            if ref.isdigit():
                user_filter |= Q(id=int(ref))
            user = CustomUser.objects.filter(user_filter).first()
            if user:
                recent_app = NewLicenseApplication.objects.filter(applicant=user).order_by("-created_at").first()
                if recent_app:
                    return "new_license_app", recent_app.application_id, user.id
                
                recent_renewal = RenewalApplication.objects.filter(applicant=user).order_by("-created_at").first()
                if recent_renewal:
                    return "renewal_app", recent_renewal.application_id, user.id

                recent_sbm = SalesmanBarmanModel.objects.filter(applicant=user).order_by("-created_at").first()
                if recent_sbm:
                    return "salesman_barman_app", recent_sbm.application_id, user.id

                return "licensee", user.id, user.id

            # 3. Check if it's a License ID directly
            license_obj = License.objects.filter(license_id__iexact=ref).first()
            if license_obj:
                user_id = license_obj.applicant_id if license_obj.applicant else None
                if license_obj.source_type == "new_license_application" and license_obj.source_object_id:
                    app = NewLicenseApplication.objects.filter(application_id__iexact=license_obj.source_object_id).first()
                    if app:
                        return "new_license_app", app.application_id, user_id
                
                return "license", license_obj.license_id, user_id

            # 4. Fallbacks if no prefix matched but exists in DB
            app = NewLicenseApplication.objects.filter(application_id__iexact=ref).first()
            if app:
                user_id = app.applicant_id if app.applicant else None
                return "new_license_app", app.application_id, user_id

            renewal = RenewalApplication.objects.filter(application_id__iexact=ref).first()
            if renewal:
                user_id = renewal.applicant_id if renewal.applicant else None
                return "renewal_app", renewal.application_id, user_id

        except Exception:
            pass

        return None, None, None

    if search_type == "payment":
        from models.transactional.payment_gateway.models import PaymentBilldeskTransaction
        from models.transactional.wallet.models import WalletTransaction
        import datetime
        import re
        
        results = []
        amount_query = None
        try:
            amount_query = float(query)
        except ValueError:
            pass
            
        date_query = None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                date_query = datetime.datetime.strptime(query, fmt).date()
                break
            except ValueError:
                pass

        # Parse partial date queries database-agnostically
        year_match = re.match(r'^(\d{4})$', query)
        month_year_match = re.match(r'^(\d{4})[-/](\d{1,2})$', query) or re.match(r'^(\d{1,2})[-/](\d{4})$', query)
        
        bd_date_q = Q()
        w_date_q = Q()
        
        if date_query:
            bd_date_q = Q(transaction_date__date=date_query)
            w_date_q = Q(created_at__date=date_query)
        elif year_match:
            y = int(year_match.group(1))
            bd_date_q = Q(transaction_date__year=y)
            w_date_q = Q(created_at__year=y)
        elif month_year_match:
            g1, g2 = month_year_match.groups()
            if len(g1) == 4:
                y, m = int(g1), int(g2)
            else:
                y, m = int(g2), int(g1)
            if 1 <= m <= 12:
                bd_date_q = Q(transaction_date__year=y, transaction_date__month=m)
                w_date_q = Q(created_at__year=y, created_at__month=m)

        bd_q = Q(utr__icontains=query) | Q(transaction_id_no_hoa__icontains=query) | Q(payer_id__icontains=query)
        if amount_query is not None:
            bd_q |= Q(transaction_amount=amount_query)
        if date_query or year_match or month_year_match:
            bd_q |= bd_date_q

        try:
            bd_txs = PaymentBilldeskTransaction.objects.filter(bd_q)
            bd_txs = apply_date_filters(bd_txs, "transaction_date")
            bd_txs = bd_txs.order_by("-transaction_date")[:30]
        except Exception:
            bd_q_safe = Q(utr__icontains=query) | Q(transaction_id_no_hoa__icontains=query) | Q(payer_id__icontains=query)
            if amount_query is not None:
                bd_q_safe |= Q(transaction_amount=amount_query)
            bd_txs = PaymentBilldeskTransaction.objects.filter(bd_q_safe)
            bd_txs = apply_date_filters(bd_txs, "transaction_date")
            bd_txs = bd_txs.order_by("-transaction_date")[:30]

        for tx in bd_txs:
            status_map = {"S": "Success", "F": "Failed", "P": "Pending"}
            status = status_map.get(tx.payment_status, "Pending")
            
            purpose = "Application Fee"
            if tx.payment_module_code == "002":
                purpose = "Renewal Fee"
            elif tx.payment_module_code == "999":
                purpose = "Wallet Recharge"

            applicant_name = resolve_applicant_name(tx.payer_id)
            applicant_suffix = f" | Applicant: {applicant_name}" if applicant_name != "N/A" else ""
            
            target_type, target_id, user_id = resolve_payment_target_info(tx.payer_id)
            if not target_type and tx.payer_id and "/" not in str(tx.payer_id):
                target_type = "licensee"
                target_id = tx.payer_id

            results.append({
                "type": "payment",
                "id": tx.utr or tx.transaction_id_no_hoa or "N/A",
                "title": f"BillDesk: {tx.utr or tx.transaction_id_no_hoa or 'N/A'}",
                "subtitle": f"Amount: ₹{tx.transaction_amount} | Module: {purpose} | App ID: {tx.payer_id}",
                "status": status,
                "meta": {
                    "transaction_id": tx.utr or tx.transaction_id_no_hoa or "N/A",
                    "amount": str(tx.transaction_amount),
                    "payment_type": "BillDesk Gateway",
                    "created_at": tx.transaction_date.strftime("%Y-%m-%d %H:%M:%S") if tx.transaction_date else "N/A",
                    "application_id": tx.payer_id,
                    "applicant_name": applicant_name,
                    "target_type": target_type,
                    "target_id": target_id,
                    "user_id": user_id
                }
            })
            if applicant_suffix:
                results[-1]["subtitle"] = f"{results[-1]['subtitle']}{applicant_suffix}"

        w_q = Q(transaction_id__icontains=query) | Q(reference_no__icontains=query) | Q(licensee_id__icontains=query)
        if amount_query is not None:
            w_q |= Q(amount=amount_query)
        if date_query or year_match or month_year_match:
            w_q |= w_date_q

        try:
            w_txs = WalletTransaction.objects.filter(w_q)
            w_txs = apply_date_filters(w_txs, "created_at")
            w_txs = w_txs.order_by("-created_at")[:30]
        except Exception:
            w_q_safe = Q(transaction_id__icontains=query) | Q(reference_no__icontains=query) | Q(licensee_id__icontains=query)
            if amount_query is not None:
                w_q_safe |= Q(amount=amount_query)
            w_txs = WalletTransaction.objects.filter(w_q_safe)
            w_txs = apply_date_filters(w_txs, "created_at")
            w_txs = w_txs.order_by("-created_at")[:30]

        for tx in w_txs:
            status = "Success"
            if tx.payment_status.lower() == "failed":
                status = "Failed"
            elif tx.payment_status.lower() in ("pending", "p"):
                status = "Pending"

            reference = tx.reference_no or tx.licensee_id
            applicant_name = resolve_applicant_name(reference)
            applicant_suffix = f" | Applicant: {applicant_name}" if applicant_name != "N/A" else ""
                
            target_type, target_id, user_id = resolve_payment_target_info(reference)
            if not target_type and tx.licensee_id:
                target_type, target_id, user_id = resolve_payment_target_info(tx.licensee_id)
            if not target_type and reference and "/" not in str(reference):
                target_type = "licensee"
                target_id = reference

            display_txn_id = tx.transaction_id
            if display_txn_id and not str(display_txn_id).startswith("BILLDESK") and len(display_txn_id) == 24:
                from datetime import timedelta
                time_margin = timedelta(hours=2)
                candidates = [c for c in [str(tx.user_id).strip(), str(tx.licensee_id).strip()] if c]
                bd_match = PaymentBilldeskTransaction.objects.filter(
                    payer_id__in=candidates,
                    payment_status="S",
                    transaction_amount=tx.amount,
                    transaction_date__gte=tx.created_at - time_margin,
                    transaction_date__lte=tx.created_at + time_margin
                ).order_by("-transaction_date").first()
                if bd_match:
                    display_txn_id = bd_match.utr

            results.append({
                "type": "payment",
                "id": display_txn_id or "N/A",
                "title": f"Wallet: {display_txn_id or 'N/A'}",
                "subtitle": f"Amount: ₹{tx.amount} | Type: {tx.transaction_type} | App/Ref ID: {tx.reference_no or tx.licensee_id}",
                "status": status,
                "meta": {
                    "transaction_id": display_txn_id or "N/A",
                    "amount": str(tx.amount),
                    "payment_type": f"Wallet {tx.transaction_type}",
                    "created_at": tx.created_at.strftime("%Y-%m-%d %H:%M:%S") if tx.created_at else "N/A",
                    "application_id": tx.reference_no or tx.licensee_id,
                    "applicant_name": applicant_name,
                    "target_type": target_type,
                    "target_id": target_id,
                    "user_id": user_id
                }
            })
            if applicant_suffix:
                results[-1]["subtitle"] = f"{results[-1]['subtitle']}{applicant_suffix}"

        results.sort(key=lambda x: x["meta"]["created_at"], reverse=True)
        return Response({"results": results})

    # Query expansion suffix (e.g. if NA/1101/2026-27/0014 -> 1101/2026-27/0014)
    suffix = query
    prefixes = ['NLA', 'NLI', 'LRA', 'LA', 'SBM', 'SB', 'NA']
    
    # Check if query starts with a prefix and slash
    upper_query = query.upper()
    matched_prefix = None
    has_specific_prefix = False
    for p in prefixes:
        if upper_query.startswith(p + "/"):
            suffix = query[len(p)+1:]
            matched_prefix = p
            has_specific_prefix = True
            break

    # Look up payment transaction matches in registry mode
    matched_nla_ids = set()
    matched_renewal_ids = set()
    matched_sbm_ids = set()
    matched_licensee_ids = set()
    matched_payment_metas = {}

    try:
        from models.transactional.payment_gateway.models import PaymentBilldeskTransaction
        from models.transactional.wallet.models import WalletTransaction
        
        bd_matches = PaymentBilldeskTransaction.objects.filter(
            Q(utr__icontains=query) | Q(transaction_id_no_hoa__icontains=query)
        )[:20]
        for tx in bd_matches:
            ref = (tx.payer_id or "").strip()
            if ref:
                ref_upper = ref.upper()
                matched_payment_metas[ref_upper] = {
                    "transaction_id": tx.utr or tx.transaction_id_no_hoa or "N/A",
                    "payment_type": "BillDesk Gateway"
                }
                if ref_upper.startswith(("NLA/", "NA/", "NLI/")):
                    matched_nla_ids.add(ref)
                elif ref_upper.startswith(("LRA/", "LA/")):
                    matched_renewal_ids.add(ref)
                elif ref_upper.startswith(("SBM/", "SB/", "RSBM/")):
                    matched_sbm_ids.add(ref)
                else:
                    matched_licensee_ids.add(ref)
                
        w_matches = WalletTransaction.objects.filter(
            Q(transaction_id__icontains=query)
        )[:20]
        for tx in w_matches:
            ref = (tx.reference_no or "").strip()
            if ref:
                ref_upper = ref.upper()
                matched_payment_metas[ref_upper] = {
                    "transaction_id": tx.transaction_id or "N/A",
                    "payment_type": f"Wallet {tx.transaction_type}"
                }
                if ref_upper.startswith(("NLA/", "NA/", "NLI/")):
                    matched_nla_ids.add(ref)
                elif ref_upper.startswith(("LRA/", "LA/")):
                    matched_renewal_ids.add(ref)
                elif ref_upper.startswith(("SBM/", "SB/", "RSBM/")):
                    matched_sbm_ids.add(ref)
                else:
                    matched_licensee_ids.add(ref)
    except Exception:
        pass

    results = []

    # Helper function to get linked NLA ID for different objects
    def get_linked_nla_id(obj):
        if isinstance(obj, License):
            if obj.source_application and isinstance(obj.source_application, NewLicenseApplication):
                return obj.source_application.application_id
            if obj.applicant:
                nla = NewLicenseApplication.objects.filter(applicant=obj.applicant).first()
                if nla:
                    return nla.application_id
        elif isinstance(obj, RenewalApplication):
            if obj.old_license_id:
                lic = License.objects.filter(license_id=obj.old_license_id).first()
                if lic and lic.source_application and isinstance(lic.source_application, NewLicenseApplication):
                    return lic.source_application.application_id
            if obj.applicant:
                nla = NewLicenseApplication.objects.filter(applicant=obj.applicant).first()
                if nla:
                    return nla.application_id
        elif isinstance(obj, SalesmanBarmanModel):
            if obj.new_license_application:
                return obj.new_license_application.application_id
            if obj.license:
                if obj.license.source_application and isinstance(obj.license.source_application, NewLicenseApplication):
                    return obj.license.source_application.application_id
            if obj.applicant:
                nla = NewLicenseApplication.objects.filter(applicant=obj.applicant).first()
                if nla:
                    return nla.application_id
        return None

    # Determine what to search based on prefix category
    search_users = True
    search_licenses = True
    search_new_apps = True
    search_renewals = True
    search_sbm = True

    if has_specific_prefix:
        if matched_prefix in ['SBM', 'SB']:
            search_users = False
            search_renewals = False
            search_new_apps = False  # Linked NLA will be found via linked_nla_ids
            search_licenses = True
        elif matched_prefix in ['LRA', 'LA']:
            search_users = False
            search_licenses = False
            search_new_apps = False
            search_sbm = False
        elif matched_prefix in ['NLA', 'NLI', 'NA']:
            search_users = False
            search_renewals = False
            search_sbm = False
            search_licenses = True

    # 1. Search Users (Licensees)
    if search_users:
        users = CustomUser.objects.annotate(
            full_name=Concat(Coalesce('first_name', Value('')), Value(' '), Coalesce('last_name', Value('')))
        ).filter(
            Q(id__in=matched_licensee_ids) |
            Q(username__in=matched_licensee_ids) |
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(phone_number__icontains=query) |
            Q(full_name__icontains=query)
        )
        users = apply_date_filters(users, "date_joined")
        users = apply_role_filter(users, "role__name")
        users = users[:15]

        for u in users:
            applicant_name = get_user_display_name(u)
            meta = {
                "user_id": u.id,
                "email": u.email,
                "username": u.username,
                "applicant_name": applicant_name
            }
            u_id_str = str(u.id)
            u_user_upper = u.username.upper().strip() if u.username else ""
            if u_id_str in matched_payment_metas:
                meta["transaction_id"] = matched_payment_metas[u_id_str]["transaction_id"]
                meta["payment_type"] = matched_payment_metas[u_id_str]["payment_type"]
            elif u_user_upper in matched_payment_metas:
                meta["transaction_id"] = matched_payment_metas[u_user_upper]["transaction_id"]
                meta["payment_type"] = matched_payment_metas[u_user_upper]["payment_type"]
                
            results.append({
                "type": "licensee",
                "id": u.id,
                "title": f"{u.first_name} {u.last_name} ({u.username})",
                "subtitle": f"Email: {u.email} | Phone: {u.phone_number} | Username: {u.username}",
                "status": "Active" if u.is_active else "Inactive",
                "meta": meta
            })
    else:
        users = []

    # 2. Search Licenses
    if search_licenses:
        if has_specific_prefix and matched_prefix in ['SBM', 'SB']:
            lic_filter = Q(license_id__icontains=query) | (Q(license_id__icontains=suffix) & (Q(license_id__startswith="SB/") | Q(license_id__startswith="SBM/")))
        elif has_specific_prefix and matched_prefix in ['NLA', 'NLI', 'NA']:
            lic_filter = Q(license_id__icontains=query) | (Q(license_id__icontains=suffix) & (Q(license_id__startswith="NA/") | Q(license_id__startswith="NLI/") | Q(license_id__startswith="NLA/")))
        else:
            lic_filter = Q(license_id__icontains=query) | Q(license_id__icontains=suffix)

        licenses = License.objects.annotate(
            full_name=Concat(Coalesce('applicant__first_name', Value('')), Value(' '), Coalesce('applicant__last_name', Value('')))
        ).filter(
            lic_filter |
            Q(applicant__username__icontains=query) |
            Q(applicant__phone_number__icontains=query) |
            Q(full_name__icontains=query)
        )
        licenses = apply_date_filters(licenses, "issue_date")
        licenses = apply_category_filter(licenses, "license_category__license_category")
        licenses = licenses.order_by("-issue_date")[:15]
    else:
        licenses = []

    # 3. Search Renewal Applications
    if search_renewals:
        renewal_apps = RenewalApplication.objects.annotate(
            full_name=Concat(Coalesce('applicant__first_name', Value('')), Value(' '), Coalesce('applicant__last_name', Value('')))
        ).filter(
            Q(application_id__in=matched_renewal_ids) |
            Q(application_id__icontains=query) |
            Q(application_id__icontains=suffix) |
            Q(old_license_id__icontains=query) |
            Q(old_license_id__icontains=suffix) |
            Q(applicant__username__icontains=query) |
            Q(applicant__phone_number__icontains=query) |
            Q(full_name__icontains=query)
        )
        renewal_apps = apply_date_filters(renewal_apps, "created_at")
        renewal_apps = apply_category_filter(renewal_apps, "license_category__license_category")
        renewal_apps = renewal_apps.order_by("-created_at")[:15]
    else:
        renewal_apps = []

    # 4. Search Salesman/Barman Applications
    if search_sbm:
        sbm_apps = SalesmanBarmanModel.objects.annotate(
            full_name=Concat(Coalesce('firstName', Value('')), Value(' '), Coalesce('lastName', Value(''))),
            applicant_full_name=Concat(Coalesce('applicant__first_name', Value('')), Value(' '), Coalesce('applicant__last_name', Value('')))
        ).filter(
            Q(application_id__in=matched_sbm_ids) |
            Q(application_id__icontains=query) |
            Q(application_id__icontains=suffix) |
            Q(firstName__icontains=query) |
            Q(lastName__icontains=query) |
            Q(mobileNumber__icontains=query) |
            Q(emailId__icontains=query) |
            Q(applicant__username__icontains=query) |
            Q(applicant__phone_number__icontains=query) |
            Q(full_name__icontains=query) |
            Q(applicant_full_name__icontains=query)
        )
        sbm_apps = apply_date_filters(sbm_apps, "created_at")
        sbm_apps = apply_role_filter(sbm_apps, "role")
        sbm_apps = sbm_apps.order_by("-created_at")[:15]
    else:
        sbm_apps = []

    # Collect linked NLA IDs
    linked_nla_ids = set()
    for lic in licenses:
        nid = get_linked_nla_id(lic)
        if nid:
            linked_nla_ids.add(nid)
    for r in renewal_apps:
        nid = get_linked_nla_id(r)
        if nid:
            linked_nla_ids.add(nid)
    for s in sbm_apps:
        nid = get_linked_nla_id(s)
        if nid:
            linked_nla_ids.add(nid)
    linked_nla_ids.update(matched_nla_ids)

    # 5. Search New License Applications (matching directly or linked to any matched sub-records)
    nla_filter = Q(application_id__in=linked_nla_ids)
    if search_new_apps:
        nla_filter |= (
            Q(application_id__in=matched_nla_ids) |
            Q(application_id__icontains=query) |
            Q(application_id__icontains=suffix) |
            Q(applicant__username__icontains=query) |
            Q(applicant__phone_number__icontains=query) |
            Q(establishment_name__icontains=query) |
            Q(mobile_number__icontains=query) |
            Q(full_name__icontains=query)
        )

    new_apps = NewLicenseApplication.objects.annotate(
        full_name=Concat(Coalesce('applicant__first_name', Value('')), Value(' '), Coalesce('applicant__last_name', Value('')))
    ).filter(
        nla_filter
    )
    new_apps = apply_date_filters(new_apps, "created_at")
    new_apps = apply_category_filter(new_apps, "license_category__license_category")
    new_apps = new_apps.order_by("-created_at")[:15]

    for app in new_apps:
        applicant_name = get_user_display_name(app.applicant) if app.applicant else "Unknown"
        meta = {
            "application_id": app.application_id,
            "is_approved": app.is_approved,
            "created_at": app.created_at.strftime("%Y-%m-%d") if app.created_at else "N/A",
            "applicant_name": applicant_name
        }
        
        app_id_upper = app.application_id.upper().strip()
        if app_id_upper in matched_payment_metas:
            meta["transaction_id"] = matched_payment_metas[app_id_upper]["transaction_id"]
            meta["payment_type"] = matched_payment_metas[app_id_upper]["payment_type"]
            
        results.append({
            "type": "new_license_app",
            "id": app.application_id,
            "title": f"New App: {app.application_id}",
            "subtitle": f"Establishment: {app.establishment_name or 'N/A'} | Applicant: {applicant_name}",
            "status": app.current_stage.name if app.current_stage else "Draft",
            "meta": meta
        })

    # Add License results
    for lic in licenses:
        applicant_name = get_user_display_name(lic.applicant) if lic.applicant else "Unknown"
        nla_id = get_linked_nla_id(lic)
        nla_suffix = f" | Linked NLA: {nla_id}" if nla_id else ""
        results.append({
            "type": "license",
            "id": lic.license_id,
            "title": f"License: {lic.license_id}",
            "subtitle": f"Applicant: {applicant_name} | Category: {lic.license_category.license_category if lic.license_category else 'N/A'}{nla_suffix}",
            "status": "Active" if lic.is_active else "Expired/Inactive",
            "meta": {
                "license_id": lic.license_id,
                "valid_up_to": lic.valid_up_to.strftime("%Y-%m-%d") if lic.valid_up_to else "N/A",
                "applicant_id": lic.applicant.id if lic.applicant else None,
                "application_id": nla_id,
                "applicant_name": applicant_name
            }
        })

    # Add Renewal Application results
    for app in renewal_apps:
        applicant_name = get_user_display_name(app.applicant) if app.applicant else "Unknown"
        nla_id = get_linked_nla_id(app)
        nla_suffix = f" | Linked NLA: {nla_id}" if nla_id else ""
        meta = {
            "application_id": nla_id,
            "renewal_app_id": app.application_id,
            "is_approved": app.is_approved,
            "created_at": app.created_at.strftime("%Y-%m-%d") if app.created_at else "N/A",
            "applicant_name": applicant_name
        }
        
        app_id_upper = app.application_id.upper().strip()
        if app_id_upper in matched_payment_metas:
            meta["transaction_id"] = matched_payment_metas[app_id_upper]["transaction_id"]
            meta["payment_type"] = matched_payment_metas[app_id_upper]["payment_type"]
            
        results.append({
            "type": "renewal_app",
            "id": app.application_id,
            "title": f"Renewal App: {app.application_id}",
            "subtitle": f"Old License: {app.old_license_id or 'N/A'}{nla_suffix} | Applicant: {applicant_name}",
            "status": app.current_stage.name if app.current_stage else "Draft",
            "meta": meta
        })

    # Add Salesman/Barman Application results
    for app in sbm_apps:
        applicant_name = f"{app.firstName} {app.lastName}"
        nla_id = get_linked_nla_id(app)
        nla_suffix = f" | Linked NLA: {nla_id}" if nla_id else ""
        meta = {
            "application_id": nla_id,
            "sbm_app_id": app.application_id,
            "is_approved": app.is_approved,
            "created_at": app.created_at.strftime("%Y-%m-%d") if app.created_at else "N/A",
            "applicant_name": applicant_name
        }
        
        app_id_upper = app.application_id.upper().strip()
        if app_id_upper in matched_payment_metas:
            meta["transaction_id"] = matched_payment_metas[app_id_upper]["transaction_id"]
            meta["payment_type"] = matched_payment_metas[app_id_upper]["payment_type"]
            
        results.append({
            "type": "salesman_barman_app",
            "id": app.application_id,
            "title": f"Salesman/Barman App: {app.application_id}",
            "subtitle": f"Name: {applicant_name} | Role: {app.role or 'N/A'}{nla_suffix} | Mobile: {app.mobileNumber or 'N/A'}",
            "status": app.current_stage.name if app.current_stage else "Draft",
            "meta": meta
        })

    return Response({"results": results})


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@permission_classes([IsAuthenticated])
def single_window_licensee_detail(request, user_id):
    user_id_str = str(user_id).strip()
    if user_id_str.isdigit():
        u = get_object_or_404(CustomUser, id=int(user_id_str))
    else:
        u = get_object_or_404(CustomUser, username__iexact=user_id_str)

    user_data = {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "phone_number": u.phone_number,
        "role_name": u.role.name if u.role else "Licensee",
        "district_name": u.district.district if u.district else "N/A",
        "subdivision_name": u.subdivision.subdivision if u.subdivision else "N/A",
        "address": u.address or "N/A",
        "is_active": u.is_active,
        "is_staff": u.is_staff,
        "is_superuser": u.is_superuser,
        "date_joined": u.date_joined.strftime("%Y-%m-%d %H:%M:%S") if u.date_joined else "N/A"
    }

    # Fetch User Licenses
    licenses = License.objects.filter(applicant=u).order_by("-issue_date")
    lic_list = []
    for lic in licenses:
        lic_list.append({
            "license_id": lic.license_id,
            "category": lic.license_category.license_category if lic.license_category else "N/A",
            "subcategory": lic.license_sub_category.description if lic.license_sub_category else "N/A",
            "issue_date": lic.issue_date.strftime("%Y-%m-%d %H:%M:%S") if lic.issue_date else "N/A",
            "valid_up_to": lic.valid_up_to.strftime("%Y-%m-%d %H:%M:%S") if lic.valid_up_to else "N/A",
            "is_active": lic.is_active
        })

    # Fetch New License Applications
    new_apps = NewLicenseApplication.objects.filter(applicant=u).order_by("-created_at")
    new_apps_list = []
    for app in new_apps:
        new_apps_list.append({
            "application_id": app.application_id,
            "establishment_name": app.establishment_name,
            "current_stage": app.current_stage.name if app.current_stage else "Draft",
            "is_approved": app.is_approved,
            "is_license_fee_paid": app.is_license_fee_paid,
            "is_security_fee_paid": app.is_security_fee_paid,
            "created_at": app.created_at.strftime("%Y-%m-%d %H:%M:%S") if app.created_at else "N/A"
        })

    # Fetch Renewal Applications
    renewal_apps = RenewalApplication.objects.filter(applicant=u).order_by("-created_at")
    renewal_apps_list = []
    for app in renewal_apps:
        renewal_apps_list.append({
            "application_id": app.application_id,
            "old_license_id": app.old_license_id,
            "current_stage": app.current_stage.name if app.current_stage else "Draft",
            "is_approved": app.is_approved,
            "is_license_fee_paid": app.is_license_fee_paid,
            "is_security_fee_paid": app.is_security_fee_paid,
            "created_at": app.created_at.strftime("%Y-%m-%d %H:%M:%S") if app.created_at else "N/A"
        })

    # Fetch Salesman/Barman Applications
    sbm_apps = SalesmanBarmanModel.objects.filter(applicant=u).order_by("-created_at")
    sbm_apps_list = []
    for app in sbm_apps:
        sbm_apps_list.append({
            "application_id": app.application_id,
            "role": app.role,
            "name": f"{app.firstName} {app.lastName}",
            "current_stage": app.current_stage.name if app.current_stage else "Draft",
            "is_approved": app.is_approved,
            "is_print_fee_paid": app.is_print_fee_paid,
            "created_at": app.created_at.strftime("%Y-%m-%d %H:%M:%S") if app.created_at else "N/A"
        })

    return Response({
        "user": user_data,
        "licenses": lic_list,
        "new_applications": new_apps_list,
        "renewal_applications": renewal_apps_list,
        "salesman_barman_applications": sbm_apps_list
    })


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@permission_classes([IsAuthenticated])
def single_window_new_app_detail(request, application_id):
    app = get_object_or_404(NewLicenseApplication, application_id=application_id)

    # Pending stage/role info
    pending_at_role = "N/A"
    pending_at_stage = app.current_stage.name if app.current_stage else "Draft"
    if app.current_stage and not app.is_approved:
        try:
            from auth.workflow.models import StagePermission
            perm = StagePermission.objects.filter(stage=app.current_stage, can_process=True).first()
            if perm and perm.role:
                pending_at_role = perm.role.name
        except Exception:
            pass

    # Find issued license directly linked to this application (Main License)
    issued_license = None
    main_lic = License.objects.filter(source_type='new_license_application', source_object_id=app.application_id).first()
    
    # If not found directly, check if applicant has any license starting with NA/ or NLI/ or NLA/ (main license prefixes)
    if not main_lic and app.applicant:
        main_lic = License.objects.filter(
            applicant=app.applicant
        ).filter(
            Q(license_id__startswith="NA/") | Q(license_id__startswith="NLI/") | Q(license_id__startswith="NLA/")
        ).order_by("-issue_date").first()
        
    if main_lic:
        issued_license = {
            "license_id": main_lic.license_id,
            "license_category": main_lic.license_category.license_category if main_lic.license_category else "N/A",
            "license_sub_category": main_lic.license_sub_category.description if main_lic.license_sub_category else "N/A",
            "issue_date": main_lic.issue_date.strftime("%Y-%m-%d") if main_lic.issue_date else "N/A",
            "valid_up_to": main_lic.valid_up_to.strftime("%Y-%m-%d") if main_lic.valid_up_to else "N/A",
            "is_active": main_lic.is_active,
        }

    # Find additional licenses (like salesman/barman SB/) belonging to the applicant
    additional_licenses = []
    if app.applicant:
        other_lics = License.objects.filter(applicant=app.applicant).order_by("-issue_date")
        for lic in other_lics:
            # Skip the main license to avoid duplication
            if main_lic and lic.license_id == main_lic.license_id:
                continue
            additional_licenses.append({
                "license_id": lic.license_id,
                "license_category": lic.license_category.license_category if lic.license_category else "N/A",
                "license_sub_category": lic.license_sub_category.description if lic.license_sub_category else "N/A",
                "issue_date": lic.issue_date.strftime("%Y-%m-%d") if lic.issue_date else "N/A",
                "valid_up_to": lic.valid_up_to.strftime("%Y-%m-%d") if lic.valid_up_to else "N/A",
                "is_active": lic.is_active,
            })

    # Find renewal applications for this applicant
    renewal_list = []
    if app.applicant:
        renewals = RenewalApplication.objects.filter(applicant=app.applicant).order_by("-created_at")
        for r in renewals:
            # Renewal pending stage
            r_pending = "N/A"
            if r.current_stage and not r.is_approved:
                try:
                    from auth.workflow.models import StagePermission
                    rp = StagePermission.objects.filter(stage=r.current_stage, can_process=True).first()
                    if rp and rp.role:
                        r_pending = rp.role.name
                except Exception:
                    pass
            renewal_list.append({
                "application_id": r.application_id,
                "old_license_id": r.old_license_id,
                "current_stage": r.current_stage.name if r.current_stage else "Draft",
                "is_approved": r.is_approved,
                "is_license_fee_paid": r.is_license_fee_paid,
                "is_security_fee_paid": r.is_security_fee_paid,
                "pending_at_role": r_pending,
                "created_at": r.created_at.strftime("%Y-%m-%d") if r.created_at else "N/A",
                "history": serialize_workflow_history(r),
                "objections": serialize_objections(r),
                "payments": serialize_payment_transactions(r.application_id),
            })

    # Find salesman/barman applications for this applicant
    sbm_list = []
    if app.applicant:
        sbms = SalesmanBarmanModel.objects.filter(applicant=app.applicant).order_by("-created_at")
        for s in sbms:
            s_pending = "N/A"
            if s.current_stage and not s.is_approved:
                try:
                    from auth.workflow.models import StagePermission
                    sp = StagePermission.objects.filter(stage=s.current_stage, can_process=True).first()
                    if sp and sp.role:
                        s_pending = sp.role.name
                except Exception:
                    pass
            sbm_list.append({
                "application_id": s.application_id,
                "name": f"{s.firstName} {s.lastName}",
                "role": s.role,
                "current_stage": s.current_stage.name if s.current_stage else "Draft",
                "is_approved": s.is_approved,
                "is_print_fee_paid": s.is_print_fee_paid,
                "pending_at_role": s_pending,
                "created_at": s.created_at.strftime("%Y-%m-%d") if s.created_at else "N/A",
                "license_id": s.license.license_id if s.license else (issued_license["license_id"] if issued_license else "N/A"),
                "history": serialize_workflow_history(s),
                "objections": serialize_objections(s),
                "payments": serialize_payment_transactions(s.application_id),
            })

    data = {
        "application_id": app.application_id,
        "applicant_name": f"{app.applicant.first_name} {app.applicant.last_name}".strip() if app.applicant else "N/A",
        "applicant_username": app.applicant.username if app.applicant else "N/A",
        "applicant_email": app.applicant.email if app.applicant else "N/A",
        "applicant_phone": app.mobile_number or (app.applicant.phone_number if app.applicant else "N/A"),
        "establishment_name": app.establishment_name,
        "license_category": app.license_category.license_category if app.license_category else "N/A",
        "license_sub_category": app.license_sub_category.description if app.license_sub_category else "N/A",
        "excise_district": app.site_district.district if app.site_district else "N/A",
        "current_stage": pending_at_stage,
        "pending_at_role": pending_at_role,
        "is_approved": app.is_approved,
        "is_license_fee_paid": app.is_license_fee_paid,
        "is_security_fee_paid": app.is_security_fee_paid,
        "created_at": app.created_at.strftime("%Y-%m-%d %H:%M:%S") if app.created_at else "N/A",
        "updated_at": app.updated_at.strftime("%Y-%m-%d %H:%M:%S") if app.updated_at else "N/A",
        "shop_address": app.business_address or "N/A",
        "pan_number": app.pan or "N/A",
        "phone_number": app.mobile_number or "N/A",
        # Related records
        "issued_license": issued_license,
        "additional_licenses": additional_licenses,
        "renewal_applications": renewal_list,
        "salesman_barman_applications": sbm_list,
        # Workflow
        "history": serialize_workflow_history(app),
        "objections": serialize_objections(app),
        "payments": serialize_payment_transactions(app.application_id)
    }
    return Response(data)



@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@permission_classes([IsAuthenticated])
def single_window_renewal_app_detail(request, application_id):
    app = get_object_or_404(RenewalApplication, application_id=application_id)

    data = {
        "application_id": app.application_id,
        "old_license_id": app.old_license_id,
        "applicant_name": f"{app.applicant.first_name} {app.applicant.last_name}" if app.applicant else "N/A",
        "applicant_email": app.applicant.email if app.applicant else "N/A",
        "license_category": app.license_category.license_category if app.license_category else "N/A",
        "license_sub_category": app.license_sub_category.description if app.license_sub_category else "N/A",
        "current_stage": app.current_stage.name if app.current_stage else "Draft",
        "is_approved": app.is_approved,
        "is_license_fee_paid": app.is_license_fee_paid,
        "is_security_fee_paid": app.is_security_fee_paid,
        "created_at": app.created_at.strftime("%Y-%m-%d %H:%M:%S") if app.created_at else "N/A",
        "updated_at": app.updated_at.strftime("%Y-%m-%d %H:%M:%S") if app.updated_at else "N/A",
        "history": serialize_workflow_history(app),
        "objections": serialize_objections(app),
        "payments": serialize_payment_transactions(app.application_id)
    }
    return Response(data)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@permission_classes([IsAuthenticated])
def single_window_license_detail(request, license_id):
    lic = get_object_or_404(License, license_id=license_id)

    data = {
        "license_id": lic.license_id,
        "applicant_name": f"{lic.applicant.first_name} {lic.applicant.last_name}" if lic.applicant else "N/A",
        "applicant_username": lic.applicant.username if lic.applicant else "N/A",
        "applicant_email": lic.applicant.email if lic.applicant else "N/A",
        "applicant_phone": lic.applicant.phone_number if lic.applicant else "N/A",
        "applicant_id": lic.applicant.id if lic.applicant else None,
        "license_category": lic.license_category.license_category if lic.license_category else "N/A",
        "license_sub_category": lic.license_sub_category.description if lic.license_sub_category else "N/A",
        "issue_date": lic.issue_date.strftime("%Y-%m-%d %H:%M:%S") if lic.issue_date else "N/A",
        "valid_up_to": lic.valid_up_to.strftime("%Y-%m-%d %H:%M:%S") if lic.valid_up_to else "N/A",
        "is_active": lic.is_active,
    }
    return Response(data)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@permission_classes([IsAuthenticated])
def single_window_salesman_barman_detail(request, application_id):
    app = get_object_or_404(SalesmanBarmanModel, application_id=application_id)

    data = {
        "application_id": app.application_id,
        "applicant_name": f"{app.applicant.first_name} {app.applicant.last_name}" if app.applicant else "N/A",
        "applicant_email": app.applicant.email if app.applicant else "N/A",
        "license_id": app.license.license_id if app.license else "N/A",
        "firstName": app.firstName,
        "middleName": app.middleName or "",
        "lastName": app.lastName,
        "role": app.role,
        "mobileNumber": app.mobileNumber,
        "emailId": app.emailId,
        "aadhaar": app.aadhaar,
        "pan": app.pan,
        "address": app.address,
        "current_stage": app.current_stage.name if app.current_stage else "Draft",
        "is_approved": app.is_approved,
        "is_print_fee_paid": app.is_print_fee_paid,
        "print_count": app.print_count,
        "created_at": app.created_at.strftime("%Y-%m-%d %H:%M:%S") if app.created_at else "N/A",
        "updated_at": app.updated_at.strftime("%Y-%m-%d %H:%M:%S") if app.updated_at else "N/A",
        "history": serialize_workflow_history(app),
        "objections": serialize_objections(app),
        "payments": serialize_payment_transactions(app.application_id)
    }
    return Response(data)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@permission_classes([IsAuthenticated])
def single_window_latest_created(request):
    # 1. Fetch latest users (Admin Users only, excluding licensees)
    users = CustomUser.objects.exclude(role__name='Licensee').order_by("-date_joined")[:50]
    users_list = []
    for u in users:
        users_list.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "phone_number": u.phone_number,
            "role_name": u.role.name if u.role else "Licensee",
            "is_active": u.is_active,
            "date_joined": u.date_joined.strftime("%Y-%m-%d %H:%M:%S") if u.date_joined else "N/A"
        })

    # 2. Fetch ONLY New License Applications for the Licenses & Applications tab
    records = []
    new_apps = NewLicenseApplication.objects.all().order_by("-created_at")[:100]
    for app in new_apps:
        applicant_name = f"{app.applicant.first_name} {app.applicant.last_name}".strip() if app.applicant else "Unknown"
        applicant_username = app.applicant.username if app.applicant else "N/A"

        # Find issued license for this applicant (if application approved)
        issued_license_id = None
        license_is_active = False
        license_valid_up_to = "N/A"
        if app.is_approved and app.applicant:
            lic = License.objects.filter(applicant=app.applicant).order_by("-issue_date").first()
            if lic:
                issued_license_id = lic.license_id
                license_is_active = lic.is_active
                license_valid_up_to = lic.valid_up_to.strftime("%Y-%m-%d") if lic.valid_up_to else "N/A"

        # Determine where application is pending (current stage role)
        pending_at = "N/A"
        if app.current_stage and not app.is_approved:
            try:
                from auth.workflow.models import StagePermission
                perm = StagePermission.objects.filter(stage=app.current_stage, can_process=True).first()
                if perm and perm.role:
                    pending_at = perm.role.name
            except Exception:
                pass

        records.append({
            "type": "new_license_app",
            "id": app.application_id,
            "application_id": app.application_id,
            "establishment_name": app.establishment_name or "N/A",
            "applicant_name": applicant_name,
            "applicant_username": applicant_username,
            "license_category": app.license_category.license_category if app.license_category else "N/A",
            "current_stage": app.current_stage.name if app.current_stage else "Draft",
            "is_approved": app.is_approved,
            "issued_license_id": issued_license_id,
            "license_is_active": license_is_active,
            "license_valid_up_to": license_valid_up_to,
            "pending_at": pending_at,
            "created_at": app.created_at.strftime("%Y-%m-%d") if app.created_at else "N/A",
            "meta": {
                "application_id": app.application_id
            }
        })

    # 3. Fetch Deactivated Users
    deactivated = CustomUser.objects.filter(is_active=False).order_by("-date_joined")[:50]
    deactivated_list = []
    for u in deactivated:
        deactivated_list.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "phone_number": u.phone_number,
            "role_name": u.role.name if u.role else "Licensee",
            "is_active": u.is_active,
            "date_joined": u.date_joined.strftime("%Y-%m-%d %H:%M:%S") if u.date_joined else "N/A"
        })

    return Response({
        "users": users_list,
        "records": records,
        "deactivated_users": deactivated_list
    })

