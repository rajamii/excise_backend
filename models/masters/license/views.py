from django.utils.timezone import now
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from django.contrib.contenttypes.models import ContentType
from rest_framework.permissions import IsAuthenticated
from rest_framework import status, generics
from auth.roles.permissions import HasAppPermission
from .models import License
from models.transactional.new_license_application.models import NewLicenseApplication
from .serializers import LicenseSerializer, LicenseDetailSerializer, MyLicenseDetailsSerializer

@permission_classes([HasAppPermission('license', 'view')])
@api_view(['GET'])
def list_licenses(request):
    """
    List all licenses.
    """
    licenses = License.objects.all()
    serializer = LicenseSerializer(licenses, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

@permission_classes([HasAppPermission('license', 'view')])
@api_view(['GET'])
@parser_classes([JSONParser])
def print_license_view(request, license_id):
    license = get_object_or_404(License, license_id=license_id)

    can_print, fee = license.can_print_license()

    if not can_print:
        return Response({
            "error": "Print limit exceeded. Please pay ₹500 to continue printing.",
            "fee_required": fee
        }, status=403)

    if fee > 0 and not license.is_print_fee_paid:
        return Response({"error": "₹500 fee not paid yet."}, status=403)

    license.record_license_print(fee_paid=(fee > 0))

    return Response({
        "success": "License printed.",
        "print_count": license.print_count
    })


@permission_classes([HasAppPermission('license', 'view')])
@api_view(['GET'])
def license_detail(request, license_id):
   
    license = get_object_or_404(License, license_id=license_id)
    serializer = LicenseDetailSerializer(license)
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('license', 'view')])
@api_view(['GET'])
def active_licensees(request):

    district_code = request.query_params.get('district_code', None)
    license_category = request.query_params.get('license_category', None)
    mode = request.query_params.get('mode', None)
    
    licensees = License.objects.filter(
        is_active=True,
        valid_up_to__gte=now().date()
        ).select_related(
        'excise_district',
        'license_category',
        'source_content_type'
    )

    if district_code:
        licensees = licensees.filter(excise_district__district_code=district_code)

    if license_category:
        licensees = licensees.filter(license_category_id=license_category)

    data = []

    for license in licensees:
        source_app = license.source_application

        if source_app:
            if hasattr(source_app, 'establishment_name'):
                establishment_name = source_app.establishment_name

            if hasattr(source_app, 'mode_of_operation'):
                mode_of_operation = source_app.mode_of_operation

            if mode:
                mode_formatted = mode.capitalize()
                if mode_of_operation != mode_formatted:
                    continue

            if mode and mode_of_operation == "N/A":
                continue

        data.append({
            "licenseeId": license.license_id,
            "id": license.license_id,
            "establishmentName": establishment_name,
            "license_category": license.license_category.license_category,
            "district": license.excise_district.district,
            "district_code": license.excise_district.district_code,
            "valid_up_to": license.valid_up_to.strftime("%Y-%m-%d"),
            "mode_of_operation": mode_of_operation,
            "status": "Active"
        })
    return Response(data, status=status.HTTP_200_OK)

class MyLicensesListView(generics.ListAPIView):
   
    serializer_class = MyLicenseDetailsSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        new_app_ct = ContentType.objects.get_for_model(NewLicenseApplication)

        user_app_ids = NewLicenseApplication.objects.filter(
            applicant=user
        ).values_list('application_id', flat=True)

        # Primary match: direct applicant linkage on License.
        qs_by_applicant = License.objects.filter(
            applicant=user,
            source_content_type=new_app_ct
        )

        # Compatibility fallback: match by source_object_id from user's applications.
        qs_by_source_object = License.objects.filter(
            source_content_type=new_app_ct,
            source_object_id__in=user_app_ids
        )

        return (qs_by_applicant | qs_by_source_object).distinct().select_related(
            'license_category',
            'license_sub_category',
            'excise_district'
        )
