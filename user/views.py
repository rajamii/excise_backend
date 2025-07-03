from django.contrib.auth.models import User
from .models import CustomUser
import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view
from .helpers import (
    update_user_details,
    delete_user_by_username,
)
from captcha.models import CaptchaStore
from .serializers import UserRegistrationSerializer, LoginSerializer, UserUpdateSerializer
from .otp import get_new_otp, verify_otp
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from captcha.helpers import captcha_image_url
from roles.views import is_role_capable_of
from roles.models import Role
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated

@api_view(['GET'])
def get_captcha(request):

    hashkey = CaptchaStore.generate_key()
    imageurl = captcha_image_url(hashkey)

    send_response = Response({
        'key': hashkey,
        'image_url': imageurl
    })
    return send_response

class TokenRefreshAPI(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        original_response = super().post(request, *args, **kwargs)
        return Response({
            'success': True,
            'status_code': status.HTTP_200_OK,
            'message': 'Token refreshed successfully',
            'access': original_response.data.get('access')  # Must be `access`
        }, status=status.HTTP_200_OK)

'''
 UserAPI class handles user registration, fetching user data,
 updating user details, and deleting user accounts.
'''


class UserRegistrationAPI(APIView):
    def post(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "User registered successfully",
                "username": user.username
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
from rest_framework.permissions import IsAuthenticated

class CurrentUserAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        role = user.role

        user_data = {
            'username': user.username,
            'first_name': user.first_name,
            'middle_name': user.middle_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone_number': user.phone_number,
            'district': user.district,
            'subdivision': user.subdivision,
            'role': role.name if role else None,
            'address': user.address,
            'created_by': user.created_by.username if user.created_by else None,
#            'permissions': {
#                'company_registration_access': role.company_registration_access if role else 'none',
#                'contact_us_access': role.contact_us_access if role else 'none',
#                'license_application_access': role.license_application_access if role else 'none',
#                'masters_access': role.masters_access if role else 'none',
#                'roles_access': role.roles_access if role else 'none',
#                'salesman_barman_registration_access': role.salesman_barman_registration_access if role else 'none',
#                'user_access': role.user_access if role else 'none',
#            }
        }
        return Response(user_data, status=status.HTTP_200_OK)

class UserDetailAPI(APIView):
    def get(self, request, username=None, *args, **kwargs):
        if request.user.username != username:
            if not is_role_capable_of(request, Role.READ, 'user'):
                return Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            user = CustomUser.objects.get(username=username)
            user_data = {
                'username': user.username,
                'first_name': user.first_name,
                'middle_name': user.middle_name,
                'last_name': user.last_name,
                'email': user.email,
                'phone_number': user.phone_number,
                'district': user.district,
                'subdivision': user.subdivision,
                'role': user.role.name if user.role else None,
                'address': user.address,
                'created_by': user.created_by.username if user.created_by else None,
            }
            return Response(user_data, status=status.HTTP_200_OK)
        except CustomUser.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

class UserListAPI(APIView):

    def get(self, request):
        if not is_role_capable_of(request, Role.READ, 'user'):
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        users = CustomUser.objects.all()
        data = [{
            'username': user.username,
            'first_name': user.first_name,
            'middle_name': user.middle_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone_number': user.phone_number,
            'district': user.district,
            'subdivision': user.subdivision,
            'created_by': user.created_by.username if user.created_by else None,
            'role': user.role.name if user.role else None,
            
        } for user in users]
        return Response(data, status=status.HTTP_200_OK)

class UserUpdateAPI(APIView):

    def put(self, request, username):
        if not is_role_capable_of(request, Role.READ_WRITE, 'user'):
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        user = get_object_or_404(CustomUser, username=username)
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': f'User {username} updated successfully'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserDeleteAPI(APIView):
    
    def delete(self, request, username):
        if not is_role_capable_of(request, Role.READ_WRITE, 'user'):
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        user = get_object_or_404(CustomUser, username=username)
        user.delete()
        return Response({'message': f'User {username} deleted successfully'}, status=status.HTTP_204_NO_CONTENT)


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
            'statusCode': status.HTTP_200_OK,
            'message': 'User logged in successfully',
            'authenticated_user': {
                'username': validated_data['username'],
                'access': validated_data['access'],
                'refresh': validated_data['refresh'],
            },
        }
        return Response(response_data, status=status.HTTP_200_OK)

# LogoutAPI handles the user logout by invalidating the refresh token.

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

class LogoutAPI(APIView):
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)

            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response({"message": "User logged out successfully"}, status=status.HTTP_205_RESET_CONTENT)

        except TokenError as e:
            # Handle already blacklisted or invalid token
            return Response({"message": "Token already blacklisted or invalid"}, status=status.HTTP_205_RESET_CONTENT)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

# Send OTP API

@api_view(['POST'])
def send_otp_API(request):
    phone_number = request.data.get('phone_number')
    if not phone_number:
        return Response({'error': 'Phone number is required for OTP login'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = CustomUser.objects.get(phone_number=phone_number)
    except CustomUser.DoesNotExist:
        return Response({'error': 'User with this phone number does not exist'}, status=status.HTTP_404_NOT_FOUND)

    otp_obj = get_new_otp(phone_number)
    # In production, send otp_obj.otp via SMS, do NOT return it in the API response!
    return Response({
        'otp_id': str(otp_obj.id),
        'otp': otp_obj.otp 
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
def verify_otp_API(request):
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
                'phone_number': user.phone_number,
                'access': access_token,
                'refresh': refresh_token,
            },
        }
        return Response(response_data, status=status.HTTP_200_OK)
    else:
        return Response({'error': message}, status=status.HTTP_401_UNAUTHORIZED)