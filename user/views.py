from django.contrib.auth.models import User
from .models import CustomUser
from django.contrib.auth import authenticate , login , logout

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
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                }
                return JsonResponse(user_data, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return JsonResponse({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            users = CustomUser.objects.all()
            user_list = [{'username': user.username, 'email': user.email, 'first_name': user.first_name, 'last_name': user.last_name} for user in users]
            return JsonResponse(user_list, safe=False, status=status.HTTP_200_OK)




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


class LogoutAPI(View):

    def post(self, request, *args, **kwargs):

        logout(request)
        return JsonResponse({'message': 'Logout successful'}, status=status.HTTP_200_OK)
