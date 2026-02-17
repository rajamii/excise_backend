from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenRefreshView
from django.shortcuts import get_object_or_404
from captcha.helpers import captcha_image_url
from captcha.models import CaptchaStore
from typing import cast

from auth.roles.permissions import make_permission, HasAppPermission
from auth.user.models import CustomUser, LicenseeProfile
from auth.user.serializer import (
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    LoginSerializer,
    LicenseeSignupSerializer,
    LicenseeProfileSerializer,
)
from auth.user.otp import (
    get_new_otp, verify_otp,
    mark_phone_as_verified, clear_phone_verified, is_phone_verified,
)
from models.transactional.logs.models import UserActivity
from models.transactional.logs.signals import get_client_ip


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
        'pan_number', 'father_name', 'dob', 'gender', 'nationality',
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
        'father_name':        request.data['father_name'],
        'dob':                request.data['dob'],
        'gender':             request.data['gender'],
        'nationality':        request.data['nationality'],
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
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [make_permission('user', 'view')]


class UserDetailView(generics.RetrieveAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [make_permission('user', 'view')]


class CurrentUserAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class UserUpdateView(generics.UpdateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserUpdateSerializer
    permission_classes = [make_permission('user', 'update')]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
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

        self.perform_destroy(instance)
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
            CustomUser.objects.get(phone_number=phone_number)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'User with this phone number does not exist'},
                status=status.HTTP_404_NOT_FOUND
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
            return Response(
                {'error': 'User does not exist in the database'},
                status=status.HTTP_404_NOT_FOUND
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