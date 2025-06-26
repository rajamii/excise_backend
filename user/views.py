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
from .serializers import UserRegistrationSerializer, LoginSerializer
from .otp import get_new_otp, verify_otp
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from captcha.helpers import captcha_image_url
from roles.views import is_role_capable_of
from roles.models import Role

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
    # TokenRefreshAPI class handles the token refresh functionality
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        return response({
            'success': True,
            'statusCode': status.HTTP_200_OK,
            'message': 'Token refreshed successfully',
            'new_access_token': response.data['access']
        }, status=status.HTTP_200_OK)

'''
 UserAPI class handles user registration, fetching user data,
 updating user details, and deleting user accounts.
'''


class UserAPI(APIView):
    # POST: Register a new user
    def post(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "User registered successfully",
                "username": user.username
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # GET: Retrieve user info
    def get(self, request, username=None, *args, **kwargs):

        if request.user.username != username:

            if is_role_capable_of(request=request,
                                  operation=Role.READ,
                                  model='user') is False:

                return Response(status=status.HTTP_401_UNAUTHORIZED)

        if username:
            try:
                user = CustomUser.objects.get(username=username)
                user_data = {  # Structure user data for response
                    'username': user.username,
                    'firstName': user.first_name,
                    'middleName': user.middle_name,
                    'lastName': user.last_name,
                    'email': user.email,
                    'phoneNumber': user.phonenumber,
                    'district': user.district,
                    'subDivision': user.subdivision,
                    'role': user.role.name if user.role else None,
                    'address': user.address,
                    'createdBy': user.created_by.username if user.created_by else None,
                }
                return Response(user_data, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            user = request.user
            if user.is_authenticated:
                user_data = {  # Structure logged-in user's data for response
                    'username': user.username,
                    'firstName': user.first_name,
                    'middleName': user.middle_name,
                    'lastName': user.last_name,
                    'email': user.email,
                    'phoneNumber': user.phonenumber,
                    'district': user.district,
                    'subDivision': user.subdivision,
                    'role': user.role.name if user.role else None,
                    'address': user.address,
                    'createdBy': user.created_by.username if user.created_by else None,
                }
                return Response(user_data, status=status.HTTP_200_OK)
            else:
                return Response({"detail": "User not authenticated."}, status=status.HTTP_401_UNAUTHORIZED)

        # Case: /user/detail/<username>/
        try:
            user = CustomUser.objects.get(username=query_username)
            return Response(self.serialize_user(user), status=status.HTTP_200_OK)
        except CustomUser.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    # PUT: Update user details by username
    def put(self, request, username, *args, **kwargs):
        if is_role_capable_of(request=request,
                              operation=Role.READ_WRITE,
                              model='user') is False:

            return Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            data = request.data
            success = update_user_details(
                username,
                # new_username=data.get('username'),
                new_email=data.get('email'),
                new_first_name=data.get('first_name'),
                new_last_name=data.get('last_name'),
                new_password=data.get('password'),
            )
            if success:
                return Response({'message': 'User updated successfully'}, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'User not found or update failed'}, status=status.HTTP_400_BAD_REQUEST)
        except json.JSONDecodeError:
            return Response({'error': 'Invalid JSON data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # DELETE: Delete user by username
    def delete(self, request, username, *args, **kwargs):
        if is_role_capable_of(request=request,
                              operation=Role.READ_WRITE,
                              model='user') is False:

            return Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            delete_user_by_username(username)
            return Response({'message': 'User deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

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


class LogoutAPI(APIView):

    # POST method for logging out by blacklisting the refresh token
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)

            token = RefreshToken(refresh_token)
            token.blacklist()  # Blacklist the refresh token

            return Response({"message": "User logged out successfully"}, status=status.HTTP_205_RESET_CONTENT)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# Send OTP API

@api_view(['POST'])
def send_otp_API(request):
    phonenumber = request.data.get('phonenumber')
    if not phonenumber:
        return Response({'error': 'Phone number is required for OTP login'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = CustomUser.objects.get(phonenumber=phonenumber)
    except CustomUser.DoesNotExist:
        return Response({'error': 'User with this phone number does not exist'}, status=status.HTTP_404_NOT_FOUND)

    otp_obj = get_new_otp(phonenumber)
    # In production, send otp_obj.otp via SMS, do NOT return it in the API response!
    return Response({'otp_id': str(otp_obj.id)}, status=status.HTTP_200_OK)

@api_view(['POST'])
def verify_otp_API(request):
    phonenumber = request.data.get('phonenumber')
    otp_input = request.data.get('otp')
    otp_id = request.data.get('otp_id')

    if not (phonenumber and otp_input and otp_id):
        return Response({'error': 'Phone number, OTP, and otp_id are required'}, status=status.HTTP_400_BAD_REQUEST)

    success, message = verify_otp(otp_id, phonenumber, otp_input)
    if success:
        try:
            user = CustomUser.objects.get(phonenumber=phonenumber)
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
                'phonenumber': user.phonenumber,
                'access': access_token,
                'refresh': refresh_token,
            },
        }
        return Response(response_data, status=status.HTTP_200_OK)
    else:
        return Response({'error': message}, status=status.HTTP_401_UNAUTHORIZED)