from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import *
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import NotFound
from django.contrib.auth import authenticate
from captcha.models import CaptchaStore
from captcha.helpers import captcha_image_url
from django.http import JsonResponse
from masters.models import *

   
def get_captcha(request):
    hashkey = CaptchaStore.generate_key()
    imageurl = captcha_image_url(hashkey)

    response = JsonResponse({
        'key': hashkey,
        'image_url': imageurl
    })
    return response        


class DashboardCountView(APIView):
    def get(self, request, *args, **kwargs):
        user = request.user
        user_role = user.role
        data = {}

        if user_role == 'site_admin':
            data['district_count'] = District.objects.filter(
                IsActive=True).count()
            data['subdivision_count'] = Subdivision.objects.filter(
                IsActive=True).count()
           


        return JsonResponse(data)    
