from django.utils.timezone import now
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from django.http import Http404
from urllib.parse import quote
import hashlib
import secrets
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from django.contrib.contenttypes.models import ContentType
from rest_framework.permissions import IsAuthenticated
from rest_framework import status, generics
from auth.roles.permissions import HasAppPermission
from django.core import signing
from .models import License, LicenseValidationToken
from .master_license_form_terms import MasterLicenseFormTerms
from models.transactional.new_license_application.models import NewLicenseApplication
from .serializers import LicenseSerializer, LicenseDetailSerializer, MyLicenseDetailsSerializer
from django.db import transaction


def _normalize_role_name(raw: str | None) -> str:
    return str(raw or '').strip().lower().replace('-', '_').replace(' ', '_')


def _require_site_admin(request) -> bool:
    # Extra guard: these endpoints are intended for Site Admin only.
    if getattr(request.user, 'is_superuser', False):
        return True
    role = getattr(request.user, 'role', None)
    if _normalize_role_name(getattr(role, 'name', None)) == 'site_admin':
        return True
    return False

def _resolve_license(identifier: str) -> License:
    """
    Resolve a License by either its `license_id` OR by `source_object_id` (application id).
    This supports screens that pass application ids like NLI/... or LIC/... instead of NA/.../LA/... ids.
    """
    token = str(identifier or "").strip()
    if not token:
        raise Http404("License not found")

    direct = License.objects.filter(license_id=token).first()
    if direct:
        return direct

    by_source = License.objects.filter(source_object_id=token).order_by("-printed_on", "-issue_date").first()
    if by_source:
        return by_source

    raise Http404("License not found")


def _build_validation_link(request, *, license_obj: License, nonce: str) -> tuple[str, str, str]:
    source = str(getattr(license_obj, "source_type", "") or "").strip()
    application_id = str(getattr(license_obj, "source_object_id", "") or "").strip() or str(license_obj.license_id)
    signing_payload = {"applicationId": application_id, "source": source, "nonce": nonce}
    signed_code = signing.dumps(signing_payload, salt="final-license")
    validation_url = request.build_absolute_uri(f"/v/{quote(signed_code, safe=':')}/")
    verification_id = hashlib.sha256(signed_code.encode("utf-8")).hexdigest()[:12]
    return signed_code, validation_url, verification_id

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
    license = _resolve_license(license_id)

    can_print, fee = license.can_print_license()

    if not can_print:
        return Response({
            "error": "Print limit exceeded. Please pay ₹500 to continue printing.",
            "fee_required": fee
        }, status=403)

    if fee > 0 and not license.is_print_fee_paid:
        return Response({"error": "₹500 fee not paid yet."}, status=403)

    license.record_license_print(fee_paid=(fee > 0))

    # Create a per-print validation token so the printed QR/link remains verifiable forever.
    nonce = secrets.token_hex(16)
    signed_code, validation_url, verification_id = _build_validation_link(request, license_obj=license, nonce=nonce)
    try:
        LicenseValidationToken.objects.create(
            license=license,
            nonce=nonce,
            signed_code=signed_code,
            validation_url=validation_url,
            verification_id=verification_id,
        )
    except Exception:
        nonce = secrets.token_hex(16)
        signed_code, validation_url, verification_id = _build_validation_link(request, license_obj=license, nonce=nonce)
        LicenseValidationToken.objects.create(
            license=license,
            nonce=nonce,
            signed_code=signed_code,
            validation_url=validation_url,
            verification_id=verification_id,
        )

    license.validation_nonce = nonce
    license.validation_nonce_updated_at = now()
    license.save(update_fields=["validation_nonce", "validation_nonce_updated_at"])

    return Response({
        "success": "License printed.",
        "print_count": license.print_count,
        "is_print_fee_paid": license.is_print_fee_paid,
        "fee_required": fee,
        "nonce": nonce,
        "verificationId": verification_id,
        "validationCode": signed_code,
        "validationPdfUrl": validation_url,
    })

@permission_classes([HasAppPermission('license', 'view')])
@api_view(['POST'])
@parser_classes([JSONParser])
def pay_print_fee_view(request, license_id):
    """
    Marks the duplicate print fee (â‚¹500) as paid for the next print only.
    After printing, the token is consumed and `is_print_fee_paid` is reset to False.
    """
    license = _resolve_license(license_id)

    if (license.print_count or 0) < 5:
        return Response({
            "success": "No print fee required yet.",
            "print_count": license.print_count,
            "is_print_fee_paid": False,
            "fee_required": 0
        }, status=status.HTTP_200_OK)

    license.is_print_fee_paid = True
    license.print_fee_paid_on = now()
    license.save(update_fields=["is_print_fee_paid", "print_fee_paid_on"])

    return Response({
        "success": "Print fee marked as paid.",
        "print_count": license.print_count,
        "is_print_fee_paid": license.is_print_fee_paid,
        "fee_required": 500
    }, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('license', 'view')])
@api_view(['GET'])
def license_detail(request, license_id):
    license = _resolve_license(license_id)
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


@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def master_license_form_terms(request):
    """
    Site Admin helper API to view/edit `master_license_form_terms`.

    IMPORTANT:
    - `licensee_cat_code` and `licensee_scat_code` are *legacy* codes
      (old_license_cat_code / old_license_scat_code).
    - Transactional/license records continue to store master PKs; only terms lookup uses legacy codes.
    """
    if not _require_site_admin(request):
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        cat_code = int(request.query_params.get('licensee_cat_code') or request.query_params.get('cat_code') or 0)
        scat_code = int(request.query_params.get('licensee_scat_code') or request.query_params.get('scat_code') or 0)
    except Exception:
        return Response({'detail': 'Invalid codes.'}, status=status.HTTP_400_BAD_REQUEST)

    if not cat_code or scat_code is None:
        return Response({'detail': 'licensee_cat_code and licensee_scat_code are required.'}, status=status.HTTP_400_BAD_REQUEST)

    rows = (
        MasterLicenseFormTerms.objects.filter(
            licensee_cat_code=cat_code,
            licensee_scat_code=scat_code,
        )
        .order_by('sl_no')
        .values('id', 'licensee_cat_code', 'licensee_scat_code', 'sl_no', 'license_terms')
    )

    return Response(
        {
            'licensee_cat_code': cat_code,
            'licensee_scat_code': scat_code,
            'terms': list(rows),
        },
        status=status.HTTP_200_OK,
    )


@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT'])
@parser_classes([JSONParser])
def master_license_form_terms_update(request):
    """
    Replace all terms for a legacy (cat, scat) pair.

    Payload:
    {
      "licensee_cat_code": 16,
      "licensee_scat_code": 1,
      "terms": ["...", "..."]   // OR [{ "license_terms": "...", "sl_no": 1 }, ...]
    }
    """
    if not _require_site_admin(request):
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    data = request.data if isinstance(request.data, dict) else {}
    try:
        cat_code = int(data.get('licensee_cat_code') or data.get('cat_code') or 0)
        scat_code = int(data.get('licensee_scat_code') or data.get('scat_code') or 0)
    except Exception:
        return Response({'detail': 'Invalid codes.'}, status=status.HTTP_400_BAD_REQUEST)

    raw_terms = data.get('terms', [])
    if not cat_code or scat_code is None:
        return Response({'detail': 'licensee_cat_code and licensee_scat_code are required.'}, status=status.HTTP_400_BAD_REQUEST)

    terms_list: list[str] = []
    if isinstance(raw_terms, list):
        for item in raw_terms:
            if isinstance(item, str):
                terms_list.append(item)
            elif isinstance(item, dict):
                terms_list.append(str(item.get('license_terms') or '').strip())
            else:
                terms_list.append(str(item).strip())

    terms_list = [t.strip() for t in terms_list if str(t or '').strip()]

    with transaction.atomic():
        MasterLicenseFormTerms.objects.filter(
            licensee_cat_code=cat_code,
            licensee_scat_code=scat_code,
        ).delete()

        objs = [
            MasterLicenseFormTerms(
                licensee_cat_code=cat_code,
                licensee_scat_code=scat_code,
                sl_no=i + 1,
                license_terms=term,
                user_id=str(getattr(request.user, 'username', '') or 'admin')[:50] or 'admin',
            )
            for i, term in enumerate(terms_list)
        ]
        if objs:
            MasterLicenseFormTerms.objects.bulk_create(objs)

    rows = (
        MasterLicenseFormTerms.objects.filter(
            licensee_cat_code=cat_code,
            licensee_scat_code=scat_code,
        )
        .order_by('sl_no')
        .values('id', 'licensee_cat_code', 'licensee_scat_code', 'sl_no', 'license_terms')
    )

    return Response(
        {
            'licensee_cat_code': cat_code,
            'licensee_scat_code': scat_code,
            'terms': list(rows),
        },
        status=status.HTTP_200_OK,
    )

class MyLicensesListView(generics.ListAPIView):
   
    serializer_class = MyLicenseDetailsSerializer
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        # Ensure wallet rows exist for the licensee before returning /me/ payload.
        # This is idempotent and helps recover from missed workflow signals.
        try:
            from models.transactional.wallet.wallet_initializer import initialize_wallet_balances_for_license

            for lic in self.get_queryset():
                initialize_wallet_balances_for_license(lic)
        except Exception:
            pass

        return super().list(request, *args, **kwargs)

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
