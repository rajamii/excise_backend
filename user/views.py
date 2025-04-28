from django.contrib.auth.models import User
from .models import CustomUser

import json
from django.http import JsonResponse

from django.shortcuts import render

from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response

from rest_framework import response , status

from .impl import (
    update_user_details,
    delete_user_by_username,
)

from captcha.models import CaptchaStore
from .serializer import UserRegistrationSerializer , LoginSerializer
# from django.views.decorators.csrf import csrf_protect
from .otp import OTPLIST
from rest_framework_simplejwt.tokens import RefreshToken
# from rest_framework.decorators import method_decorator



class UserAPI (APIView ):


    def post(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()  # This will create the user and generate the username
            return Response({
                "message": "User registered successfully",
                "username": user.username  # Return the generated username
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    def get(self, request, username=None, *args, **kwargs):

        
        if username:
        
            try:
                user = CustomUser.objects.get(username=username)
                user_data = {
                    'username': user.username,
                    'firstName': user.first_name,
                    'middleName': user.middle_name,
                    'lastName': user.last_name,
                    'email': user.email,
                    'phoneNumber': user.phonenumber,
                    'district': user.district,
                    'subDivision': user.subdivision,
                    'role': user.role,
                    'address': user.address,
                }
                return JsonResponse(user_data, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return JsonResponse({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:

            user = request.user
            if user.is_authenticated:
                user_data = {
                    'username': user.username,
                    'firstName': user.first_name,
                    'middleName': user.middle_name,
                    'lastName': user.last_name,
                    'email': user.email,
                    'phoneNumber': user.phonenumber,
                    'district': user.district,
                    'subDivision': user.subdivision,
                    'role': user.role,
                    'address': user.address,
                    'createdBy': user.created_by, 

                }

                return Response(user_data, status=status.HTTP_200_OK)
            else:
                return Response({"detail": "User not authenticated."}, status=status.HTTP_401_UNAUTHORIZED)



    def put(self, request, username, *args, **kwargs):
        try:
            data = json.loads(request.body)
            success = update_user_details(
                username,
                new_username=data.get('username'),
                new_email=data.get('email'),
                new_first_name=data.get('first_name'),
                new_last_name=data.get('last_name'),
                new_password=data.get('password'),
            )
            if success:
                return JsonResponse({'message': 'User updated successfully'}, status=status.HTTP_200_OK)
            else:
                return JsonResponse({'error': 'User not found or update failed'}, status=status.HTTP_400_BAD_REQUEST)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)



    def delete(self, request, username, *args, **kwargs):
        try:
            delete_user_by_username(username)
            return JsonResponse({'message': 'User deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)




class LoginAPI(APIView):

    serializer_class = LoginSerializer

    def post(self, request):

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)  # Automatically raises ValidationError if invalid

        # If validation passes, get the validated data
        validated_data = serializer.validated_data

        # Prepare the response
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


class LogoutAPI(APIView):

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)

            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response({"message": "User logged out successfully"}, status=status.HTTP_205_RESET_CONTENT)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        

static_otp_list = OTPLIST()

# @csrf_protect
def send_otp_API(request):

    if request.method == 'POST':
        username = request.POST.get('username')

        if not username :
            return JsonResponse({'error' : 'username is required for otp login'})

        try:
            user = CustomUser.objects.get(username=username)
        except User.DoesNotExist:
            return JsonResponse({'error':'user with this username does not exist'})


        if len(static_otp_list.otplist) > 0:
            static_otp_list.check_time_and_mark()
            static_otp_list.cleanup()

        otp = static_otp_list.get_new_otp(in_username=username)

        print(f"OTP : {otp.otp}" ) 
        
        return JsonResponse({'index' : otp.index})

    else:
        return JsonResponse({'error': 'Invalid request sent'})



# @api_view(['POST'])
def verify_otp_API(request):

    if request.method == 'POST':

        username = request.POST.get('username')
        otp = int( request.POST.get('otp'))
        index = int( request.POST.get('index'))

        print(index)
        print(static_otp_list.otplist[index].username)
        
        if static_otp_list.otplist[index].username == username and static_otp_list.otplist[index].otp == otp :

            user = CustomUser.objects.get(username=username)

            if not user:
                return JsonResponse({'error' : 'user does not exist in the database'})


            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)



            response_data = {
                'success': True,
                'statusCode': status.HTTP_200_OK,
                'message': 'User logged in successfully',
                'authenticated_user': {
                    'username': user.username,
                    'access': access_token,
                    'refresh': refresh_token,
                },
            }

            return JsonResponse(response_data, status=status.HTTP_200_OK)
        
        else:
            return JsonResponse({'error':' wrong otp'})
            
    
    else:
        return JsonResponse({'error': 'Invalid request'})
