from django.contrib.auth.models import User
from .models import CustomUser
import json
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import response, status
from .helpers import (
    update_user_details,
    delete_user_by_username,
)
from captcha.models import CaptchaStore
from .serializer import UserRegistrationSerializer, LoginSerializer
from .otp import OTPLIST
from rest_framework_simplejwt.tokens import RefreshToken
from captcha.helpers import captcha_image_url

def get_captcha(request):

    hashkey = CaptchaStore.generate_key()
    imageurl = captcha_image_url(hashkey)

    send_response = JsonResponse({
        'key': hashkey,
        'image_url': imageurl
    })
    return send_response


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
        query_username = username or request.query_params.get('username')

        # Case: /user/detail/all/ or ?username=all
        if query_username == "all":
            if not (request.user.is_staff or getattr(request.user, "role", "") == "site_admin"):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            users = CustomUser.objects.all()
            data = [self.serialize_user(user) for user in users]
            return Response(data, status=status.HTTP_200_OK)

        # Case: /user/detail/me/ or no username → return current user
        if not query_username or query_username == "me":
            if request.user.is_authenticated:
                return Response(self.serialize_user(request.user, include_created_by=True), status=status.HTTP_200_OK)
            return Response({"detail": "User not authenticated."}, status=status.HTTP_401_UNAUTHORIZED)

        # Case: /user/detail/<username>/
        try:
            user = CustomUser.objects.get(username=query_username)
            return Response(self.serialize_user(user), status=status.HTTP_200_OK)
        except CustomUser.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    # PUT: Update user details by username
    def put(self, request, username, *args, **kwargs):
        try:
            data = request.data
            success = update_user_details(
                username,
                new_username=data.get('username'),
                new_email=data.get('email'),
                new_first_name=data.get('first_name'),
                new_last_name=data.get('last_name'),
                new_password=data.get('password'),
            )
            if success:
                return Response({'message': 'User updated successfully'}, status=status.HTTP_200_OK)
            return Response({'error': 'User not found or update failed'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # DELETE: Delete user by username
    def delete(self, request, username, *args, **kwargs):
        try:
            delete_user_by_username(username)
            return Response({'message': 'User deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def serialize_user(self, user, include_created_by=False):
        data = {
            'username': user.username,
            'first_name': user.first_name,
            'middle_name': user.middle_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone_number': user.phone_number,
            'district': user.district,
            'subdivision': user.subdivision,
            'role': user.role,
            'address': user.address,
            'created_by': user.created_by
        }
        if include_created_by:
            data['created_by'] = user.created_by
        return data

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


# OTP Handling: Static OTP list to manage OTP requests and verification.
static_otp_list = OTPLIST()

# Send OTP API
def send_otp_API(request):
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')

        if not phone_number:
            return JsonResponse({'error': 'Phone number is required for OTP login'})

        try:
            user = CustomUser.objects.get(phone_number=phone_number)
        except CustomUser.DoesNotExist:
            return JsonResponse({'error': 'User with this phone number does not exist'})

        # Cleanup expired OTPs before generating a new one
        if static_otp_list.otplist:
            static_otp_list.check_time_and_mark()
            static_otp_list.cleanup()

        otp = static_otp_list.get_new_otp(in_phone_number=phone_number)

        print(f"OTP sent to {phone_number}: {otp.otp}")  # For debugging

        return JsonResponse({
            'index': otp.index,
            'otp': otp.otp  # Return the OTP index and OTP value
        })

    return JsonResponse({'error': 'Invalid request method'}, status=405)


# Verify OTP API
def verify_otp_API(request):
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')
        otp_input = request.POST.get('otp')
        index = request.POST.get('index')

        if not (phone_number and otp_input and index):
            return JsonResponse(
                        {'error': 'Phone number, OTP, and index are required'},
                        status=400
                        )

        try:
            otp_input = int(otp_input)
            index = int(index)
        except ValueError:
            return JsonResponse({'error': 'OTP and index must be integers'}, status=400)

        try:
            otp_obj = static_otp_list.otplist[index]
        except IndexError:
            return JsonResponse({'error': 'Invalid OTP index'}, status=400)

        if otp_obj.check_otp(otp_input, phone_number, index) and not otp_obj.is_used():
            try:
                user = CustomUser.objects.get(phone_number=phone_number)
            except CustomUser.DoesNotExist:
                return JsonResponse({'error': 'User does not exist in the database'}, status=400)

            otp_obj.used = True  # Mark OTP as used

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

            return JsonResponse(response_data, status=status.HTTP_200_OK)
        else:
            return JsonResponse({'error': 'Invalid or expired OTP'}, status=401)

    return JsonResponse({'error': 'Invalid request method'}, status=405)