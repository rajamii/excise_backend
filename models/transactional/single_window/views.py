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


def serialize_workflow_history(obj):
    hist = []
    try:
        txs = obj.transactions.all().order_by("timestamp")
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
        objections = obj.objections.all().order_by("-created_at")
        for ob in objections:
            objection_by = ob.objection_by if hasattr(ob, 'objection_by') else None
            objs.append({
                "objection_remarks": getattr(ob, 'objection_remarks', '') or "",
                "objection_by": objection_by.username if objection_by else "System",
                "objection_by_name": f"{objection_by.first_name} {objection_by.last_name}".strip() if objection_by else "System",
                "stage": ob.stage.name if hasattr(ob, 'stage') and ob.stage else "N/A",
                "reply_remarks": getattr(ob, 'reply_remarks', None) or "No reply submitted yet.",
                "is_resolved": getattr(ob, 'is_resolved', False),
                "created_at": ob.created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ob, 'created_at') and ob.created_at else "N/A"
            })
    except Exception:
        pass
    return objs


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@permission_classes([IsAuthenticated])
def single_window_search(request):
    query = request.query_params.get("query", "").strip()
    if not query:
        return Response({"results": []})

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
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(phone_number__icontains=query) |
            Q(full_name__icontains=query)
        )[:15]
        for u in users:
            results.append({
                "type": "licensee",
                "id": u.id,
                "title": f"{u.first_name} {u.last_name} ({u.username})",
                "subtitle": f"Email: {u.email} | Phone: {u.phone_number} | Username: {u.username}",
                "status": "Active" if u.is_active else "Inactive",
                "meta": {
                    "user_id": u.id,
                    "email": u.email,
                    "username": u.username
                }
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
        ).order_by("-issue_date")[:15]
    else:
        licenses = []

    # 3. Search Renewal Applications
    if search_renewals:
        renewal_apps = RenewalApplication.objects.annotate(
            full_name=Concat(Coalesce('applicant__first_name', Value('')), Value(' '), Coalesce('applicant__last_name', Value('')))
        ).filter(
            Q(application_id__icontains=query) |
            Q(application_id__icontains=suffix) |
            Q(old_license_id__icontains=query) |
            Q(old_license_id__icontains=suffix) |
            Q(applicant__username__icontains=query) |
            Q(applicant__phone_number__icontains=query) |
            Q(full_name__icontains=query)
        ).order_by("-created_at")[:15]
    else:
        renewal_apps = []

    # 4. Search Salesman/Barman Applications
    if search_sbm:
        sbm_apps = SalesmanBarmanModel.objects.annotate(
            full_name=Concat(Coalesce('firstName', Value('')), Value(' '), Coalesce('lastName', Value(''))),
            applicant_full_name=Concat(Coalesce('applicant__first_name', Value('')), Value(' '), Coalesce('applicant__last_name', Value('')))
        ).filter(
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
        ).order_by("-created_at")[:15]
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

    # 5. Search New License Applications (matching directly or linked to any matched sub-records)
    nla_filter = Q(application_id__in=linked_nla_ids)
    if search_new_apps:
        nla_filter |= (
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
    ).order_by("-created_at")[:15]

    for app in new_apps:
        applicant_name = f"{app.applicant.first_name} {app.applicant.last_name}" if app.applicant else "Unknown"
        results.append({
            "type": "new_license_app",
            "id": app.application_id,
            "title": f"New App: {app.application_id}",
            "subtitle": f"Establishment: {app.establishment_name or 'N/A'} | Applicant: {applicant_name}",
            "status": app.current_stage.name if app.current_stage else "Draft",
            "meta": {
                "application_id": app.application_id,
                "is_approved": app.is_approved,
                "created_at": app.created_at.strftime("%Y-%m-%d") if app.created_at else "N/A"
            }
        })

    # Add License results
    for lic in licenses:
        applicant_name = f"{lic.applicant.first_name} {lic.applicant.last_name}" if lic.applicant else "Unknown"
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
                "application_id": nla_id
            }
        })

    # Add Renewal Application results
    for app in renewal_apps:
        applicant_name = f"{app.applicant.first_name} {app.applicant.last_name}" if app.applicant else "Unknown"
        nla_id = get_linked_nla_id(app)
        nla_suffix = f" | Linked NLA: {nla_id}" if nla_id else ""
        results.append({
            "type": "renewal_app",
            "id": app.application_id,
            "title": f"Renewal App: {app.application_id}",
            "subtitle": f"Old License: {app.old_license_id or 'N/A'}{nla_suffix} | Applicant: {applicant_name}",
            "status": app.current_stage.name if app.current_stage else "Draft",
            "meta": {
                "application_id": nla_id,
                "renewal_app_id": app.application_id,
                "is_approved": app.is_approved,
                "created_at": app.created_at.strftime("%Y-%m-%d") if app.created_at else "N/A"
            }
        })

    # Add Salesman/Barman Application results
    for app in sbm_apps:
        applicant_name = f"{app.firstName} {app.lastName}"
        nla_id = get_linked_nla_id(app)
        nla_suffix = f" | Linked NLA: {nla_id}" if nla_id else ""
        results.append({
            "type": "salesman_barman_app",
            "id": app.application_id,
            "title": f"Salesman/Barman App: {app.application_id}",
            "subtitle": f"Name: {applicant_name} | Role: {app.role or 'N/A'}{nla_suffix} | Mobile: {app.mobileNumber or 'N/A'}",
            "status": app.current_stage.name if app.current_stage else "Draft",
            "meta": {
                "application_id": nla_id,
                "sbm_app_id": app.application_id,
                "is_approved": app.is_approved,
                "created_at": app.created_at.strftime("%Y-%m-%d") if app.created_at else "N/A"
            }
        })

    return Response({"results": results})


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@permission_classes([IsAuthenticated])
def single_window_licensee_detail(request, user_id):
    u = get_object_or_404(CustomUser, id=user_id)

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

    # Find issued license for this applicant
    issued_license = None
    if app.applicant:
        lic = License.objects.filter(applicant=app.applicant).order_by("-issue_date").first()
        if lic:
            issued_license = {
                "license_id": lic.license_id,
                "license_category": lic.license_category.license_category if lic.license_category else "N/A",
                "license_sub_category": lic.license_sub_category.description if lic.license_sub_category else "N/A",
                "issue_date": lic.issue_date.strftime("%Y-%m-%d") if lic.issue_date else "N/A",
                "valid_up_to": lic.valid_up_to.strftime("%Y-%m-%d") if lic.valid_up_to else "N/A",
                "is_active": lic.is_active,
            }

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
        "renewal_applications": renewal_list,
        "salesman_barman_applications": sbm_list,
        # Workflow
        "history": serialize_workflow_history(app),
        "objections": serialize_objections(app)
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
        "objections": serialize_objections(app)
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
        "objections": serialize_objections(app)
    }
    return Response(data)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@permission_classes([IsAuthenticated])
def single_window_latest_created(request):
    # 1. Fetch latest users (Admin/Users)
    users = CustomUser.objects.all().order_by("-date_joined")[:50]
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

    return Response({
        "users": users_list,
        "records": records
    })
