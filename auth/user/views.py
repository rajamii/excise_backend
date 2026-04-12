from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenRefreshView
from django.shortcuts import get_object_or_404
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from captcha.helpers import captcha_image_url
from captcha.models import CaptchaStore
from auth.roles.permissions import HasAppPermission, make_permission
from auth.roles.models import Role
from auth.user.models import CustomUser, LicenseeProfile, OICOfficerAssignment
from auth.user.serializer import (
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    LoginSerializer,
    LicenseeSignupSerializer,
    LicenseeProfileSerializer,
    OICOfficerCreateSerializer,
    OICOfficerUpdateSerializer,
    OICOfficerAssignmentSerializer,
    OICApprovedEstablishmentSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)
from auth.user.otp import (
    get_new_otp, verify_otp,
    mark_phone_as_verified, clear_phone_verified, is_phone_verified,
)
from models.transactional.logs.models import UserActivity
from models.transactional.logs.signals import get_client_ip
from models.transactional.new_license_application.models import NewLicenseApplication
from models.masters.supply_chain.profile.models import SupplyChainUserProfile, UserManufacturingUnit
from models.masters.license.models import License
from typing import cast
import secrets
import string
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
import binascii

User = get_user_model()

# ─────────────────────────────────────────────────────────────────────────────
# OTP endpoints
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp_for_registration(request):
    phone_number = request.data.get('phone_number')
    otp_input = request.data.get('otp')
    otp_id = request.data.get('otp_id')

    if not (phone_number and otp_input and otp_id):
        return Response(
            {'success': False, 'error': 'Missing required fields'},
            status=status.HTTP_400_BAD_REQUEST
        )

    success, message = verify_otp(otp_id, phone_number, otp_input)

    if success:
        mark_phone_as_verified(phone_number)
        return Response({'success': True, 'message': 'OTP verified successfully.'})

    return Response(
        {'success': False, 'error': message or 'OTP verification failed.'},
        status=status.HTTP_400_BAD_REQUEST
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def licensee_register_after_verification(request):
    required_fields = [
        'phone_number', 'first_name', 'last_name', 'email',
        'pan_number',
        'address', 'district', 'subdivision', 'password', 'hashkey', 'response',
    ]

    missing = [f for f in required_fields if not request.data.get(f)]
    if missing:
        return Response(
            {'success': False, 'errors': {f: ['This field is required.'] for f in missing}},
            status=status.HTTP_400_BAD_REQUEST
        )

    phone_number = request.data['phone_number']

    if not is_phone_verified(phone_number):
        return Response(
            {'success': False, 'errors': {'non_field_errors': [
                'Phone number not verified or verification expired. Please verify OTP again.'
            ]}},
            status=status.HTTP_400_BAD_REQUEST
        )

    clear_phone_verified(phone_number)

    # Validate CAPTCHA
    try:
        captcha_store = CaptchaStore.objects.get(hashkey=request.data['hashkey'])
        if captcha_store.response.strip().lower() != request.data['response'].strip().lower():
            return Response(
                {'success': False, 'errors': {'captcha': ['Invalid CAPTCHA.']}},
                status=status.HTTP_400_BAD_REQUEST
            )
        captcha_store.delete()
    except CaptchaStore.DoesNotExist:
        return Response(
            {'success': False, 'errors': {'captcha': ['Invalid CAPTCHA key.']}},
            status=status.HTTP_400_BAD_REQUEST
        )

    registration_data = {
        'email':              request.data['email'],
        'first_name':         request.data['first_name'],
        'middle_name':        request.data.get('middle_name', ''),
        'last_name':          request.data['last_name'],
        'phone_number':       phone_number,
        'address':            request.data['address'],
        'district':           request.data['district'],
        'subdivision':        request.data['subdivision'],
        'password':           request.data['password'],
        # Profile fields
        'pan_number':         request.data['pan_number'],
        'father_name':        request.data.get('father_name'),
        'dob':                request.data.get('dob'),
        'gender':             request.data.get('gender'),
        'nationality':        request.data.get('nationality'),
        'marital_status':     request.data.get('marital_status', ''),
        'residential_status': request.data.get('residential_status', ''),
    }

    serializer = LicenseeSignupSerializer(data=registration_data)
    if serializer.is_valid():
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'success': True,
            'message': 'Registration successful. You are now logged in.',
            'user': {
                'username':    user.username,
                'phoneNumber': user.phone_number,
                'email':       user.email,
                'firstName':   user.first_name,
                'lastName':    user.last_name,
            },
            'tokens': {
                'access':  str(refresh.access_token),
                'refresh': str(refresh),
            }
        }, status=status.HTTP_201_CREATED)

    return Response(
        {'success': False, 'errors': serializer.errors},
        status=status.HTTP_400_BAD_REQUEST
    )


# ─────────────────────────────────────────────────────────────────────────────
# User registration / management
# ─────────────────────────────────────────────────────────────────────────────

@permission_classes([HasAppPermission('user', 'create')])
@api_view(['POST'])
def register_user(request):
    serializer = UserCreateSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        user = cast(CustomUser, serializer.save())
        return Response(
            {'message': 'User registered successfully', 'user_id': user.username},
            status=status.HTTP_201_CREATED
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def _ensure_site_admin(request):
    if not request.user or not request.user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    if getattr(request.user, 'role_id', None) != 1:
        raise PermissionDenied("Only Site Admin can access this endpoint.")


def _ensure_site_admin_or_commissioner(request):
    if not request.user or not request.user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    role_id = getattr(request.user, 'role_id', None)
    if role_id not in {1, 10}:
        raise PermissionDenied("Only Site Admin or Commissioner can access this endpoint.")


def _derive_licensee_id(application, license_obj):
    # Always map to issued/approved license id (e.g. NA/...).
    approved_license_id = str(getattr(license_obj, 'license_id', '') or '').strip()
    if approved_license_id:
        return approved_license_id

    # Hard fallback only if license row is malformed.
    source_object_id = str(getattr(license_obj, 'source_object_id', '') or '').strip()
    if source_object_id:
        return source_object_id

    return str(getattr(application, 'application_id', '') or '').strip()


def _split_full_name(full_name: str):
    cleaned = str(full_name or '').strip()
    if not cleaned:
        return 'Officer', 'Incharge'
    parts = cleaned.split(None, 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else 'Officer'
    return first_name, last_name


def _generate_temp_password(length: int = 12):
    if length < 8:
        length = 8
    alphabet = string.ascii_letters + string.digits + '@$!%*?&'
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice('@$!%*?&'),
    ]
    password.extend(secrets.choice(alphabet) for _ in range(length - 4))
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


def _soft_delete_oic_officer(officer: CustomUser) -> None:
    timestamp_token = timezone.now().strftime('%Y%m%d%H%M%S')
    unique_suffix = str(officer.pk)

    officer.is_active = False

    if officer.email:
        local_part, _, domain_part = officer.email.partition('@')
        sanitized_local = local_part[:20] if local_part else 'deleted'
        domain_value = domain_part or 'deleted.local'
        officer.email = f"{sanitized_local}.deleted.{timestamp_token}.{unique_suffix}@{domain_value}"

    if officer.username:
        officer.username = f"deleted_oic_{timestamp_token}_{unique_suffix}"[:30]

    replacement_phone = f"9{str(officer.pk).zfill(9)[-9:]}"
    if CustomUser.objects.exclude(pk=officer.pk).filter(phone_number=replacement_phone).exists():
        replacement_phone = f"8{timestamp_token[-9:]}"
    officer.phone_number = replacement_phone

    officer.save(update_fields=['is_active', 'email', 'username', 'phone_number'])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def oic_approved_establishments(request):
    _ensure_site_admin_or_commissioner(request)

    content_type = ContentType.objects.get_for_model(NewLicenseApplication)
    licenses = (
        License.objects.filter(
            source_type='new_license_application',
            source_content_type=content_type,
            is_active=True,
        )
        .select_related('applicant')
        .order_by('-issue_date')
    )

    rows = []
    seen_applications = set()

    for license_obj in licenses:
        application = license_obj.source_application
        if not isinstance(application, NewLicenseApplication):
            continue
        if application.application_id in seen_applications:
            continue
        seen_applications.add(application.application_id)

        licensee_id = _derive_licensee_id(application, license_obj)
        district_code = str(getattr(application.site_district, 'district_code', '') or '')
        subdivision_code = str(getattr(application.site_subdivision, 'subdivision_code', '') or '')

        rows.append({
            'applicationId': application.application_id,
            'establishmentName': application.establishment_name,
            'licenseId': license_obj.license_id,
            'licenseeId': licensee_id,
            'districtCode': district_code,
            'subdivisionCode': subdivision_code,
        })

    serializer = OICApprovedEstablishmentSerializer(rows, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def oic_officer_list(request):
    _ensure_site_admin_or_commissioner(request)

    assignments = OICOfficerAssignment.objects.select_related(
        'officer',
        'approved_application',
        'license',
    ).order_by('-created_at')

    serializer = OICOfficerAssignmentSerializer(assignments, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def oic_officer_create(request):
    _ensure_site_admin(request)

    serializer = OICOfficerCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    payload = serializer.validated_data

    application = get_object_or_404(
        NewLicenseApplication,
        application_id=payload['approved_application_id']
    )
    content_type = ContentType.objects.get_for_model(NewLicenseApplication)
    license_obj = (
        License.objects.filter(
            source_type='new_license_application',
            source_content_type=content_type,
            source_object_id=str(application.application_id),
            is_active=True,
        )
        .order_by('-issue_date')
        .first()
    )
    if not license_obj:
        return Response(
            {'detail': 'No active license found for selected approved application.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    oic_role = (
        Role.objects.filter(name__iexact='officer_in_charge').first()
        or Role.objects.filter(id=7).first()
        or Role.objects.filter(name__icontains='officer').first()
    )
    if not oic_role:
        return Response(
            {'detail': 'Officer In Charge role not configured.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    first_name, last_name = _split_full_name(payload['name'])
    password = _generate_temp_password()
    address = (
        str(getattr(application, 'business_address', '') or '').strip()
        or str(getattr(application, 'present_address', '') or '').strip()
        or 'N/A'
    )
    licensee_id = _derive_licensee_id(application, license_obj)
    license_type_name = (
        str(getattr(getattr(application, 'license_type', None), 'license_type', '') or '').strip()
        or None
    )

    with transaction.atomic():
        officer = CustomUser.objects.create_user(
            email=payload['email'],
            first_name=first_name,
            middle_name='',
            last_name=last_name,
            phone_number=payload['phone_number'],
            district=application.site_district,
            subdivision=application.site_subdivision,
            address=address,
            password=password,
            role=oic_role,
            created_by=request.user,
            is_oic_managed=True,
        )

        assignment = OICOfficerAssignment.objects.create(
            officer=officer,
            approved_application=application,
            license=license_obj,
            licensee_id=licensee_id,
            establishment_name=application.establishment_name,
            created_by=request.user,
        )

        SupplyChainUserProfile.objects.update_or_create(
            user=officer,
            defaults={
                'manufacturing_unit_name': application.establishment_name,
                'licensee_id': licensee_id,
                'license_type': license_type_name,
                'address': address,
            }
        )

        UserManufacturingUnit.objects.update_or_create(
            user=officer,
            licensee_id=licensee_id,
            defaults={
                'manufacturing_unit_name': application.establishment_name,
                'license_type': license_type_name,
                'address': address,
            }
        )

    assignment_serializer = OICOfficerAssignmentSerializer(assignment)
    return Response(
        {
            'message': 'Officer created successfully.',
            'credentials': {
                'username': officer.username,
                'temporaryPassword': password,
            },
            'officer': assignment_serializer.data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def oic_officer_update(request, assignment_id):
    _ensure_site_admin(request)

    assignment = get_object_or_404(
        OICOfficerAssignment.objects.select_related('officer', 'approved_application', 'license'),
        pk=assignment_id
    )
    officer = assignment.officer

    serializer = OICOfficerUpdateSerializer(
        data=request.data,
        context={'officer': officer}
    )
    serializer.is_valid(raise_exception=True)
    payload = serializer.validated_data

    application = get_object_or_404(
        NewLicenseApplication,
        application_id=payload['approved_application_id']
    )
    content_type = ContentType.objects.get_for_model(NewLicenseApplication)
    license_obj = (
        License.objects.filter(
            source_type='new_license_application',
            source_content_type=content_type,
            source_object_id=str(application.application_id),
            is_active=True,
        )
        .order_by('-issue_date')
        .first()
    )
    if not license_obj:
        return Response(
            {'detail': 'No active license found for selected approved application.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    first_name, last_name = _split_full_name(payload['name'])
    address = (
        str(getattr(application, 'business_address', '') or '').strip()
        or str(getattr(application, 'present_address', '') or '').strip()
        or officer.address
        or 'N/A'
    )
    licensee_id = _derive_licensee_id(application, license_obj)
    license_type_name = (
        str(getattr(getattr(application, 'license_type', None), 'license_type', '') or '').strip()
        or None
    )

    with transaction.atomic():
        officer.first_name = first_name
        officer.last_name = last_name
        officer.email = payload['email']
        officer.phone_number = payload['phone_number']
        officer.district = application.site_district
        officer.subdivision = application.site_subdivision
        officer.address = address
        officer.save(update_fields=[
            'first_name',
            'last_name',
            'email',
            'phone_number',
            'district',
            'subdivision',
            'address',
        ])

        assignment.approved_application = application
        assignment.license = license_obj
        assignment.licensee_id = licensee_id
        assignment.establishment_name = application.establishment_name
        assignment.save(update_fields=[
            'approved_application',
            'license',
            'licensee_id',
            'establishment_name',
        ])

        SupplyChainUserProfile.objects.update_or_create(
            user=officer,
            defaults={
                'manufacturing_unit_name': application.establishment_name,
                'licensee_id': licensee_id,
                'license_type': license_type_name,
                'address': address,
            }
        )

        UserManufacturingUnit.objects.update_or_create(
            user=officer,
            licensee_id=licensee_id,
            defaults={
                'manufacturing_unit_name': application.establishment_name,
                'license_type': license_type_name,
                'address': address,
            }
        )

    assignment_serializer = OICOfficerAssignmentSerializer(assignment)
    return Response(
        {
            'message': 'Officer updated successfully.',
            'officer': assignment_serializer.data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def oic_officer_set_active(request, assignment_id):
    _ensure_site_admin(request)

    assignment = get_object_or_404(
        OICOfficerAssignment.objects.select_related('officer'),
        pk=assignment_id
    )
    officer = assignment.officer

    is_active = request.data.get('is_active', request.data.get('isActive'))
    if is_active in [True, False]:
        normalized = bool(is_active)
    elif isinstance(is_active, str):
        normalized = is_active.strip().lower() in {'true', '1', 'yes', 'active'}
    else:
        return Response(
            {'detail': 'is_active is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    officer.is_active = normalized
    officer.save(update_fields=['is_active'])

    assignment_serializer = OICOfficerAssignmentSerializer(assignment)
    return Response(
        {
            'message': f"Officer {'activated' if normalized else 'deactivated'} successfully.",
            'officer': assignment_serializer.data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def oic_officer_delete(request, assignment_id):
    _ensure_site_admin(request)

    assignment = get_object_or_404(
        OICOfficerAssignment.objects.select_related('officer'),
        pk=assignment_id
    )
    officer = assignment.officer

    try:
        with transaction.atomic():
            officer.delete()
        return Response({'message': 'Officer deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)
    except Exception:
        with transaction.atomic():
            _soft_delete_oic_officer(officer)
            UserManufacturingUnit.objects.filter(user=officer).delete()
            SupplyChainUserProfile.objects.filter(user=officer).delete()
            assignment.delete()
        return Response(
            {
                'message': 'Officer could not be hard deleted due to linked records. Officer has been deactivated and removed from the OIC list.'
            },
            status=status.HTTP_200_OK,
        )


# Licensee self-signup (public endpoint)
@api_view(['POST'])
@permission_classes([])
def licensee_signup(request):
    serializer = LicenseeSignupSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'success': True,
            'message': 'Registration successful. You can now log in.',
            'user': {
                'username':     user.username,
                'phone_number': user.phone_number,
                'email':        user.email,
            },
            'tokens': {
                'access':  str(refresh.access_token),
                'refresh': str(refresh),
            }
        }, status=status.HTTP_201_CREATED)

    return Response(
        {'success': False, 'errors': serializer.errors},
        status=status.HTTP_400_BAD_REQUEST
    )


class UserListView(generics.ListAPIView):
    """
    Lists all users. Requires 'user.view' permission.
    """
    queryset = CustomUser.objects.filter(is_oic_managed=False, is_active=True)
    serializer_class = UserSerializer
    permission_classes = [make_permission('user', 'view')]


class UserDetailView(generics.RetrieveAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [make_permission('user', 'view')]


class CurrentUserAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        if not user.is_active:
            return Response(
                {'detail': 'Your account is inactive. Contact administrator for login.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

class UserUpdateView(generics.UpdateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserUpdateSerializer
    permission_classes = [make_permission('user', 'update')]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Prevent silent "success" when payload contains no valid updatable fields.
        if not serializer.validated_data:
            return Response(
                {'message': 'No valid fields provided for update.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        self.perform_update(serializer)

        UserActivity.objects.create(
            user=request.user,
            activity_type=UserActivity.ActivityType.USER_UPDATE,
            target_user=instance,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            metadata={
                'updated_fields': list(serializer.validated_data.keys()),
                'target_username': instance.username,
            }
        )
        return Response({'message': 'User updated successfully'})


class UserDeleteView(generics.DestroyAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [make_permission('user', 'delete')]

    def _soft_delete_user(self, instance: CustomUser) -> None:
        timestamp_token = timezone.now().strftime('%Y%m%d%H%M%S')
        unique_suffix = str(instance.pk)

        instance.is_active = False

        if instance.email:
            local_part, _, domain_part = instance.email.partition('@')
            sanitized_local = local_part[:20] if local_part else 'deleted'
            domain_value = domain_part or 'deleted.local'
            instance.email = f"{sanitized_local}.deleted.{timestamp_token}.{unique_suffix}@{domain_value}"

        if instance.username:
            instance.username = f"deleted_{timestamp_token}_{unique_suffix}"[:30]

        # Keep phone unique after soft delete to allow reuse for new user creation.
        replacement_phone = f"9{str(instance.pk).zfill(9)[-9:]}"
        if CustomUser.objects.exclude(pk=instance.pk).filter(phone_number=replacement_phone).exists():
            replacement_phone = f"8{timestamp_token[-9:]}"
        instance.phone_number = replacement_phone

        instance.save(update_fields=['is_active', 'email', 'username', 'phone_number'])

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        UserActivity.objects.create(
            user=request.user,
            activity_type=UserActivity.ActivityType.USER_DELETE,
            target_user=instance,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            metadata={
                'deleted_username': instance.username,
                'deleted_user_id': str(instance.id),
            }
        )

        self._soft_delete_user(instance)
        return Response({'message': 'User deleted successfully'}, status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────────────────
# LicenseeProfile CRUD  (moved from core)
# ─────────────────────────────────────────────────────────────────────────────

class LicenseeProfileListView(generics.ListAPIView):
    """List all licensee profiles. Requires 'licenseeprofile.view' permission."""
    queryset = LicenseeProfile.objects.select_related('user', 'created_by')
    serializer_class = LicenseeProfileSerializer
    permission_classes = [make_permission('licenseeprofile', 'view')]


class LicenseeProfileDetailView(generics.RetrieveAPIView):
    """Retrieve a single licensee profile by pk."""
    queryset = LicenseeProfile.objects.select_related('user', 'created_by')
    serializer_class = LicenseeProfileSerializer
    permission_classes = [make_permission('licenseeprofile', 'view')]


class LicenseeProfileUpdateView(generics.UpdateAPIView):
    """
    Partially update mutable fields of a LicenseeProfile.
    Immutable fields (pan_number, father_name, dob, gender, nationality)
    are rejected by the serializer.
    """
    queryset = LicenseeProfile.objects.all()
    serializer_class = LicenseeProfileSerializer
    permission_classes = [make_permission('licenseeprofile', 'update')]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({'message': 'Licensee profile updated successfully'})


class LicenseeProfileDeleteView(generics.DestroyAPIView):
    """Delete a licensee profile (and cascade-deletes the linked user)."""
    queryset = LicenseeProfile.objects.all()
    serializer_class = LicenseeProfileSerializer
    permission_classes = [make_permission('licenseeprofile', 'delete')]

    def destroy(self, request, *args, **kwargs):
        self.perform_destroy(self.get_object())
        return Response({'message': 'Licensee profile deleted successfully'}, status=status.HTTP_204_NO_CONTENT)


class MyLicenseeProfileView(APIView):
    """
    Authenticated licensee manages their own profile.
    GET   /user/licensee-profiles/me/  -> return profile or 404
    POST  /user/licensee-profiles/me/  -> create profile
    PATCH /user/licensee-profiles/me/  -> update mutable fields
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = LicenseeProfile.objects.get(user=request.user)
            return Response(LicenseeProfileSerializer(profile).data)
        except LicenseeProfile.DoesNotExist:
            return Response(
                {'detail': 'No licensee profile found for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )

    def post(self, request):
        if LicenseeProfile.objects.filter(user=request.user).exists():
            return Response(
                {'detail': 'A licensee profile already exists. Use PATCH to update.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = LicenseeProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        try:
            profile = LicenseeProfile.objects.get(user=request.user)
        except LicenseeProfile.DoesNotExist:
            return Response(
                {'detail': 'No licensee profile found. Use POST to create one.'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = LicenseeProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(LicenseeProfileSerializer(profile).data)


# ─────────────────────────────────────────────────────────────────────────────
# Auth endpoints
# ─────────────────────────────────────────────────────────────────────────────

class LoginAPI(APIView):
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        return Response({
            'success': True,
            'status_code': status.HTTP_200_OK,
            'message': 'User logged in successfully',
            'authenticated_user': {
                'username': validated_data['username'],
                'access':   validated_data['access'],
                'refresh':  validated_data['refresh'],
            },
        })


class LogoutAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            RefreshToken(refresh_token).blacklist()
            return Response({"message": "User logged out successfully"})
        except TokenError:
            return Response({"message": "Token already blacklisted or invalid"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def get_captcha(request):
    hashkey = CaptchaStore.generate_key()
    return Response({'key': hashkey, 'image_url': captcha_image_url(hashkey)})


class TokenRefreshAPI(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        original = super().post(request, *args, **kwargs)
        return Response({
            'success': True,
            'status_code': status.HTTP_200_OK,
            'message': 'Token refreshed successfully',
            'access': original.data.get('access'),
        })


@api_view(['POST'])
def send_otp_api(request):
    phone_number = request.data.get('phone_number')
    purpose = request.data.get('purpose')

    if not phone_number:
        return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)

    if purpose != 'register':
        try:
            user = CustomUser.objects.get(phone_number=phone_number)
        except CustomUser.DoesNotExist:
            return Response({'error': 'User with this phone number does not exist'}, status=status.HTTP_404_NOT_FOUND)
        if not user.is_active:
            return Response(
                {'error': 'Your account is inactive. Contact administrator for login.'},
                status=status.HTTP_403_FORBIDDEN
            )

    if purpose == 'register':
        if CustomUser.objects.filter(phone_number=phone_number).exists():
            return Response(
                {'error': 'This phone number is already registered.'},
                status=status.HTTP_400_BAD_REQUEST
            )

    try:
        otp_obj = get_new_otp(phone_number)
        return Response({
            'otp_id': str(otp_obj.id),
            'otp': otp_obj.otp  # REMOVE IN PRODUCTION
        })
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)


@api_view(['POST'])
def verify_otp_api(request):
    phone_number = request.data.get('phone_number')
    otp_input = request.data.get('otp')
    otp_id = request.data.get('otp_id')

    if not (phone_number and otp_input and otp_id):
        return Response(
            {'error': 'Phone number, OTP, and otp_id are required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    success, message = verify_otp(otp_id, phone_number, otp_input)

    if success:
        try:
            user = CustomUser.objects.get(phone_number=phone_number)
        except CustomUser.DoesNotExist:
            return Response({'error': 'User does not exist in the database'}, status=status.HTTP_404_NOT_FOUND)

        if not user.is_active:
            return Response(
                {'error': 'Your account is inactive. Contact administrator for login.'},
                status=status.HTTP_403_FORBIDDEN
            )

        refresh = RefreshToken.for_user(user)
        return Response({
            'success': True,
            'statusCode': status.HTTP_200_OK,
            'message': 'User logged in successfully',
            'authenticated_user': {
                'access':  str(refresh.access_token),
                'refresh': str(refresh),
            },
        })

    return Response({'error': message}, status=status.HTTP_401_UNAUTHORIZED)


class PasswordResetRequestView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        serializer = self.get_serializer(data = request.data)
        serializer.is_valid(raise_exception = True)
        email = serializer.validated_data['email']

        user = User.objects.filter(email=email, is_active=True).first() #here
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            reset_link = f"{settings.PASSWORD_RESET_FRONTEND_URL}/{uid}/{token}"

            send_mail(
                subject = "Password Reset Request",
                message = f"Click the link below to reset your password:\n\n{reset_link}",
                from_email = settings.DEFAULT_FROM_EMAIL,
                recipient_list = [user.email],
                fail_silently=False,
            )
        return Response(
            {'message': 'If an account with that email exists, a password reset link has been sent.'}, 
            status=status.HTTP_200_OK
        )

class PasswordResetConfirmView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = self.get_serializer(data = request.data)
        serializer.is_valid(raise_exception = True)
        
        uidb64 = serializer.validated_data['uidb64']
        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist, binascii.Error):
            user = None
            return Response({'error': 'Invalid reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        if user is not None and default_token_generator.check_token(user, token):
            user.set_password(new_password)
            user.save()
            return Response({'message': 'Password has been reset successfully.'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)
