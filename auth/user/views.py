from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from auth.roles.permissions import make_permission
from rest_framework.permissions import IsAuthenticated, AllowAny
from auth.user.models import CustomUser
from auth.user.serializer import UserSerializer, UserCreateSerializer, LoginSerializer, LicenseeSignupSerializer
from typing import cast
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from auth.user.otp import get_new_otp, verify_otp, mark_phone_as_verified, clear_phone_verified, is_phone_verified
from captcha.helpers import captcha_image_url
from captcha.models import CaptchaStore
from rest_framework_simplejwt.views import TokenRefreshView
from ..roles.permissions import HasAppPermission
from models.transactional.logs.models import UserActivity
from models.transactional.logs.signals import get_client_ip

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
        return Response({
            'success': True,
            'message': 'OTP verified successfully.'
        }, status=status.HTTP_200_OK)
    
    # Always return a response, even on error
    return Response({
        'success': False,
        'error': message or 'OTP verification failed.'
    }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def licensee_register_after_verification(request):
    required_fields = [
        'phone_number', 'first_name', 'last_name',
        'email', 'pan_number', 'address', 'district', 'subdivision',
        'password', 'hashkey', 'response'
    ]

    missing = [field for field in required_fields if not request.data.get(field)]
    if missing:
        return Response({
            'success': False,
            'errors': {f: ['This field is required.'] for f in missing}
        }, status=status.HTTP_400_BAD_REQUEST)

    phone_number = request.data['phone_number']

    # CRITICAL: Check if phone was verified recently
    if not is_phone_verified(phone_number):
        return Response({
            'success': False,
            'errors': {'non_field_errors': ['Phone number not verified or verification expired. Please verify OTP again.']}
        }, status=status.HTTP_400_BAD_REQUEST)

    # Optional: Clear it now so can't reuse
    clear_phone_verified(phone_number)

    # Validate CAPTCHA
    hashkey = request.data['hashkey']
    response = request.data['response']
    try:
        captcha_store = CaptchaStore.objects.get(hashkey=hashkey)
        if captcha_store.response.strip().lower() != response.strip().lower():
            return Response({
                'success': False,
                'errors': {'captcha': ['Invalid CAPTCHA.']}
            }, status=status.HTTP_400_BAD_REQUEST)
        captcha_store.delete()
    except CaptchaStore.DoesNotExist:
        return Response({
            'success': False,
            'errors': {'captcha': ['Invalid CAPTCHA key.']}
        }, status=status.HTTP_400_BAD_REQUEST)

    # Register user
    registration_data = {
        'email': request.data['email'],
        'first_name': request.data['first_name'],
        'middle_name': request.data.get('middle_name', ''),
        'last_name': request.data['last_name'],
        'phone_number': phone_number,
        'pan_number': request.data['pan_number'],
        'address': request.data['address'],
        'district': request.data['district'],
        'subdivision': request.data['subdivision'],
        'password': request.data['password'],
    }

    serializer = LicenseeSignupSerializer(data=registration_data)
    if serializer.is_valid():
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'success': True,
            'message': 'Registration successful. You are now logged in.',
            'user': {
                'username': user.username,
                'phoneNumber': user.phone_number,
                'email': user.email,
                'firstName': user.first_name,
                'lastName': user.last_name
            },
            'tokens': {
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }
        }, status=status.HTTP_201_CREATED)

    return Response({
        'success': False,
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)

# User registration by staff 
@permission_classes([HasAppPermission('user', 'create')])
@api_view(['POST'])
def register_user(request):
    """
    Handles user registration.
    User registration activity is tracked via a post_save signal on the User model.
    """
    serializer = UserCreateSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        user = cast(CustomUser, serializer.save())
        # The post_save signal for the User model (defined in transactional.logs.signals)
        # will automatically handle logging the registration activity.
        return Response({
            'message': 'User registered successfully',
            'user_id': user.username,
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Licensee self-signup (public endpoint)
@api_view(['POST'])
@permission_classes([])  # Public access
def licensee_signup(request):
    
    serializer = LicenseeSignupSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()

        # Generate tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            'success': True,
            'message': 'Registration successful. You can now log in.',
            'user': {
                'username': user.username,
                'phone_number': user.phone_number,
                'email': user.email
            },
            'tokens': {
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }
        }, status=status.HTTP_201_CREATED)

    return Response({
        'success': False,
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


class UserListView(generics.ListAPIView):
    """
    Lists all users. Requires 'user.view' permission.
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [make_permission('user', 'view')]

class UserDetailView(generics.RetrieveAPIView):
    """
    Retrieves details of a single user. Requires 'user.view' permission.
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [make_permission('user', 'view')]

class CurrentUserAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

class UserUpdateView(generics.UpdateAPIView):
    """
    Updates an existing user's profile. Requires 'user.update' permission.
    Logs 'User Profile Update' activity.
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [make_permission('user', 'update')]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object() 
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        
        
        # LOGGING USER ACTIVITY: User Profile Update
        # A new UserActivity record is created to log that a user's profile
        # has been updated.
        # - 'user': The authenticated user who initiated this update request.
        # - 'activity_type': Set to USER_UPDATE.
        # - 'target_user': The specific user whose profile was modified.
        # - 'ip_address' and 'user_agent': Contextual information about the request.
        # - 'metadata': Contains details like the fields that were updated and
        #               the username of the target user.
        

        UserActivity.objects.create(
            user=request.user,  # The authenticated user who performed the update

            activity_type=UserActivity.ActivityType.USER_UPDATE,

            target_user=instance, # The user whose profile was actually updated
            
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            metadata={
                'updated_fields': list(serializer.validated_data.keys()),
                'target_username': instance.username,
                
                # Optionally log more details
                # 'request_data_summary': {k: v for k, v in request.data.items() if k not in ['password', 'confirm_password']},
            }
        )
        return Response({'message': 'User updated successfully'})

class UserDeleteView(generics.DestroyAPIView):
    """
    Deletes a user account. Requires 'user.delete' permission.
    Logs 'User Account Deletion' activity.
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [make_permission('user', 'delete')]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object() # The user being deleted

        '''
        LOGGING USER ACTIVITY: User Account Deletion
        A new UserActivity record is created to log that a user account
        has been deleted.
        - 'user': The authenticated user who initiated this delete request.
        - 'activity_type': Set to USER_DELETE.
        - 'target_user': The specific user account that was deleted.
        - 'ip_address' and 'user_agent': Contextual information about the request.
        - 'metadata': Contains details like the username and ID of the deleted user.
        '''

        UserActivity.objects.create(
            user=request.user,  # The authenticated user who performed the deletion
            activity_type=UserActivity.ActivityType.USER_DELETE,
            target_user=instance, # The user whose account was deleted
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            metadata={
                'deleted_username': instance.username,
                'deleted_user_id': str(instance.id) # Convert UUID/PK to string for metadata
            }
        )

        self.perform_destroy(instance)
        return Response({'message': 'User deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
    
# LoginAPI handles user login functionality via JWT.
class LoginAPI(APIView):
    serializer_class = LoginSerializer

    # POST method for logging in the user
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        # Automatically raises ValidationError if invalid
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data  # Extract validated data

        response_data = {
            'success': True,
            'status_code': status.HTTP_200_OK,
            'message': 'User logged in successfully',
            'authenticated_user': {
                'username': validated_data['username'],
                'access': validated_data['access'],
                'refresh': validated_data['refresh'],
            },
        }
        return Response(response_data, status=status.HTTP_200_OK)


# LogoutAPI handles the user logout by invalidating the refresh token.
class LogoutAPI(APIView):
    permission_classes = [IsAuthenticated]  # Optional

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)

            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response({"message": "User logged out successfully"}, status=status.HTTP_200_OK)

        except TokenError:
            return Response({"message": "Token already blacklisted or invalid"}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def get_captcha(request):

    hashkey = CaptchaStore.generate_key()
    image_url = captcha_image_url(hashkey)

    return Response({
        'key': hashkey,
        'image_url': image_url
    })

class TokenRefreshAPI(TokenRefreshView):
    """
    Handles JWT token refresh using refresh token.
    """
    def post(self, request, *args, **kwargs):
        original_response = super().post(request, *args, **kwargs)
        return Response({
            'success': True,
            'status_code': status.HTTP_200_OK,
            'message': 'Token refreshed successfully',
            'access': original_response.data.get('access'),
        }, status=status.HTTP_200_OK)
 
 
# Send OTP API
@api_view(['POST'])
def send_otp_api(request):
    phone_number = request.data.get('phone_number')
    purpose = request.data.get('purpose')  # New optional field: 'login' or 'register'

    if not phone_number:
        return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)

    # If purpose is 'register', skip user existence check
    if purpose != 'register':
        try:
            user = CustomUser.objects.get(phone_number=phone_number)
        except CustomUser.DoesNotExist:
            return Response({'error': 'User with this phone number does not exist'}, status=status.HTTP_404_NOT_FOUND)

    # Optional: For registration, check if phone already registered
    if purpose == 'register':
        if CustomUser.objects.filter(phone_number=phone_number).exists():
            return Response({'error': 'This phone number is already registered.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        otp_obj = get_new_otp(phone_number)
        # In production: send SMS here
        # For dev: return OTP (remove in prod!)
        return Response({
            'otp_id': str(otp_obj.id),
            'otp': otp_obj.otp  # REMOVE IN PRODUCTION
        }, status=status.HTTP_200_OK)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

@api_view(['POST'])
def verify_otp_api(request):
    phone_number = request.data.get('phone_number')
    otp_input = request.data.get('otp')
    otp_id = request.data.get('otp_id')

    if not (phone_number and otp_input and otp_id):
        return Response({'error': 'Phone number, OTP, and otp_id are required'}, status=status.HTTP_400_BAD_REQUEST)

    success, message = verify_otp(otp_id, phone_number, otp_input)
    
    if success:
        try:
            user = CustomUser.objects.get(phone_number=phone_number)
        except CustomUser.DoesNotExist:
            return Response({'error': 'User does not exist in the database'}, status=status.HTTP_404_NOT_FOUND)

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response_data = {
            'success': True,
            'statusCode': status.HTTP_200_OK,
            'message': 'User logged in successfully',
            'authenticated_user': {
                'access': access_token,
                'refresh': refresh_token,
            },
        }
        return Response(response_data, status=status.HTTP_200_OK)
    else:
        return Response({'error': message}, status=status.HTTP_401_UNAUTHORIZED)