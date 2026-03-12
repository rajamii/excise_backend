from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from auth.roles.permissions import HasAppPermission
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError, SuspiciousOperation
from django.contrib.contenttypes.models import ContentType
from .models import SiteEnquiryReport
from .serializers import SiteEnquiryReportSerializer
from auth.workflow.permissions import HasStagePermission
from models.transactional.license_application.models import LicenseApplication
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

    supply_chain_profile = getattr(user, 'supply_chain_profile', None)
    if supply_chain_profile:
        profile_license = _first_non_empty(getattr(supply_chain_profile, 'licensee_id', ''))
        if profile_license:
            return profile_license

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
        # Prevent duplicate
        if SiteEnquiryReport.objects.filter(content_type=ct, object_id=application.application_id).exists():
            return Response({"detail": "Site enquiry already submitted"}, status=400)

        try:
            serializer = SiteEnquiryReportSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(
                    content_type=ct,
                    object_id=application.application_id,
                    license_id=_resolve_license_id_for_report(request, application) or None,
                )
                return Response(serializer.data, status=201)
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
