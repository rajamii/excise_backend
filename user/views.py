from django.contrib.auth.models import User
from django.contrib.auth import authenticate , login , logout

import json
from django.http import JsonResponse

from django.shortcuts import render
from django.views import View
from rest_framework import response , status
from .impl import (
    registerUser,
    update_user_details,
    delete_user_by_username,
)

from captcha.models import CaptchaStore



class UserAPI (View ):

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            
            if User.objects.filter(username=data.get('username')).exists():

                return JsonResponse({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)

            if User.objects.filter(email=data.get('email')).exists():

                return JsonResponse({'error': 'Email already exists'}, status=status.HTTP_400_BAD_REQUEST)

            user = registerUser(
                username    = data.get('username'),
                email       = data.get('email'),
                password    = data.get('password'),
                first_name  = data.get('first_name'),
                last_name   = data.get('last_name'),
            ) 

            
            return JsonResponse({'message': 'User registered successfully'}, status=status.HTTP_201_CREATED)


        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)




    def get(self, request, username=None, *args, **kwargs):
        if username:
            try:
                user = User.objects.get(username=username)
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
            users = User.objects.all()
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




class LoginAPI(View):

    def post(self, request, *args, **kwargs):

        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')
            hashkey  = data.get('hashkey' )
            response = data.get('response')

            try:
                CaptchaStore.objects.get(hashkey=hashkey , response=response.strip().lower())

            except CaptchaStore.DoesNotExist:

                return JsonResponse({'error': 'Invalid Captcha'}, status=status.HTTP_401_UNAUTHORIZED)
                
            
            user = authenticate(request, username=username, password=password)

            if user is not None:

                login(request, user)
                return JsonResponse({'message': 'Login successful'}, status=status.HTTP_200_OK)

            else:

                return JsonResponse({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        except json.JSONDecodeError:

            return JsonResponse({'error': 'Invalid JSON data'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:

            return JsonResponse({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        
class LogoutAPI(View):

    def post(self, request, *args, **kwargs):

        logout(request)
        return JsonResponse({'message': 'Logout successful'}, status=status.HTTP_200_OK)
