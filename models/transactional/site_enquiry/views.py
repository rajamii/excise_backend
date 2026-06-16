from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from auth.roles.permissions import HasAppPermission
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError, SuspiciousOperation
from django.contrib.contenttypes.models import ContentType
from .models import SiteEnquiryReport
from .serializers import SiteEnquiryReportSerializer
from auth.workflow.permissions import HasStagePermission
from models.transactional.license_renewal_application.models import LicenseApplication
from models.transactional.new_license_application.models import NewLicenseApplication
from auth.workflow.models import WorkflowStage
from auth.workflow.services import WorkflowService


def _first_non_empty(*values):
    for value in values:
        text = str(value or '').strip()
        if text:
            return text
    return ''


def _resolve_license_id_for_report(request, application):
    explicit = _first_non_empty(
        request.data.get('license_id'),
        request.data.get('licenseId'),
    )
    if explicit:
        return explicit

    user = request.user

    manufacturing_units = getattr(user, 'manufacturing_units', None)
    if manufacturing_units is not None:
        latest_unit = manufacturing_units.order_by('-updated_at', '-created_at').first()
        if latest_unit:
            unit_license = _first_non_empty(getattr(latest_unit, 'licensee_id', ''))
            if unit_license:
                return unit_license

    oic_assignment = getattr(user, 'oic_assignment', None)
    if oic_assignment:
        assignment_license = _first_non_empty(getattr(oic_assignment, 'licensee_id', ''))
        if assignment_license:
            return assignment_license

    renewal_license = getattr(getattr(application, 'renewal_of', None), 'license_id', '')
    application_license = _first_non_empty(
        renewal_license,
        getattr(application, 'license_no', ''),
        getattr(application, 'license', ''),
    )
    if application_license:
        return application_license

    # For pre-approval flows (e.g. new license application), there is no
    # issued NA/... license yet. Persist application_id as traceable fallback.
    return _first_non_empty(getattr(application, 'application_id', ''))


@api_view(['GET', 'POST'])
@permission_classes([HasStagePermission])
@parser_classes([MultiPartParser, FormParser])
def site_enquiry_detail(request, application_id):
    
    application = None
    for model in [LicenseApplication, NewLicenseApplication]:
        try:
            application = model.objects.get(application_id=application_id)
            break
        except model.DoesNotExist:
            continue

    if not application:
        return Response({"detail": "Application not found"}, status=404)

    ct = ContentType.objects.get_for_model(application)

    if request.method == 'GET':
        try:
            report = SiteEnquiryReport.objects.get(content_type=ct, object_id=application.application_id)
            serializer = SiteEnquiryReportSerializer(report)
            return Response(serializer.data)
        except SiteEnquiryReport.DoesNotExist:
            return Response({"detail": "Site enquiry not submitted yet"}, status=404)

    elif request.method == 'POST':
        # Create OR (when reverted) allow updating existing report
        existing = SiteEnquiryReport.objects.filter(content_type=ct, object_id=application.application_id).first()
        if existing and not getattr(existing, "is_reverted", False):
            return Response({"detail": "Site enquiry already submitted"}, status=400)

        try:
            serializer = SiteEnquiryReportSerializer(instance=existing, data=request.data, partial=bool(existing))
            if serializer.is_valid():
                saved = serializer.save(
                    content_type=ct,
                    object_id=application.application_id,
                    license_id=getattr(existing, "license_id", None) or _resolve_license_id_for_report(request, application) or None,
                )
                # Clear revert flag on resubmission (keeps reverted_remarks for audit)
                if getattr(saved, "is_reverted", False):
                    saved.is_reverted = False
                    saved.save(update_fields=["is_reverted", "updated_at"])
                return Response(SiteEnquiryReportSerializer(saved).data, status=201)
            return Response(serializer.errors, status=400)
        except SuspiciousOperation as exc:
            return Response({"detail": f"Invalid upload data: {str(exc)}"}, status=400)
    

@permission_classes([HasAppPermission('license_application', 'update'), HasStagePermission])
@api_view(['GET', 'POST'])
@parser_classes([MultiPartParser, FormParser])
def level2_site_enquiry(request, application_id):
    application = get_object_or_404(LicenseApplication, pk=application_id)
    if request.method == 'GET':
        report = SiteEnquiryReport.objects.filter(application=application).first()
        serializer = SiteEnquiryReportSerializer(report) if report else None
        return Response(serializer.data if serializer else {"detail": "No site enquiry report found."})
    
    if request.user.role.name != "level_2":
        return Response({"detail": "Only level_2 can submit site enquiry."}, status=status.HTTP_403_FORBIDDEN)
    
    serializer = SiteEnquiryReportSerializer(data=request.data)
    if serializer.is_valid():
        report= serializer.save(application=application)
        target_stage = WorkflowStage.objects.filter(workflow = application.workflow, name = 'awaiting_payment').first()
        if target_stage:
            try:
                WorkflowService.advance_stage(
                    application=application,
                    user=request.user,
                    target_stage=target_stage,
                    context_data={"site_enquiry_done": True},
                    skip_permission_check=False
                )
            except ValidationError as e:
                 return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SiteEnquiryReportSerializer(report).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([HasStagePermission])
def site_enquiry_revert(request, application_id):
    """
    Joint Commissioner action: revert Site Enquiry Report back to Site Enquiry Officer.

    - Moves workflow stage Joint Commissioner -> Site Enquiry Officer using the DB transition condition
      `{"is_reverted": true}` (workflow_workflowtransition).
    - Stores remarks on `site_enquiry_report.reverted_remarks` so Site Enquiry Officer can see it while editing.
    """
    application = None
    for model in [LicenseApplication, NewLicenseApplication]:
        try:
            application = model.objects.get(application_id=application_id)
            break
        except model.DoesNotExist:
            continue

    if not application:
        return Response({"detail": "Application not found"}, status=404)

    from_stage_name = str(getattr(getattr(application, "current_stage", None), "name", "") or "").strip().lower()
    if "joint commissioner" not in from_stage_name and "jointcommissioner" not in from_stage_name.replace(" ", ""):
        return Response({"detail": "Revert is only allowed from Joint Commissioner stage."}, status=400)

    ct = ContentType.objects.get_for_model(application)
    report = SiteEnquiryReport.objects.filter(content_type=ct, object_id=application.application_id).first()
    if not report:
        return Response({"detail": "Site enquiry report not found."}, status=404)

    remarks = _first_non_empty(
        request.data.get("remarks"),
        request.data.get("reverted_remarks"),
        request.data.get("revertedRemarks"),
    )
    if not remarks:
        return Response({"detail": "Remarks are required to revert the site enquiry report."}, status=400)

    # Stage lookup within the same workflow graph
    target_stage = (
        WorkflowStage.objects.filter(workflow=application.workflow, name__iexact="Site Enquiry Officer").first()
        or WorkflowStage.objects.filter(workflow=application.workflow, name__icontains="site enquiry").first()
    )
    if not target_stage:
        return Response({"detail": "Workflow misconfigured: Site Enquiry Officer stage not found."}, status=400)

    try:
        # Mark report as reverted + persist remarks for editing
        report.is_reverted = True
        report.reverted_remarks = remarks
        report.reverted_at = timezone.now()
        report.save(update_fields=["is_reverted", "reverted_remarks", "reverted_at", "updated_at"])

        WorkflowService.advance_stage(
            application=application,
            user=request.user,
            target_stage=target_stage,
            context={"is_reverted": True},
            remarks=remarks,
        )
    except ValidationError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            "detail": "Site enquiry report reverted back to Site Enquiry Officer.",
            "current_stage": getattr(getattr(application, "current_stage", None), "id", None),
            "current_stage_name": getattr(getattr(application, "current_stage", None), "name", None),
        },
        status=200,
    )
