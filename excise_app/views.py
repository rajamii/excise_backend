from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import *
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import NotFound
from django.contrib.auth import authenticate
from captcha.models import CaptchaStore
from captcha.helpers import captcha_image_url
from django.http import JsonResponse
from otp.views import send_otp

#create views in masters 

#User Registration/Signup
class UserRegistrationView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()  # This will create the user and generate the username
            return Response({
                "message": "User registered successfully",
                "username": user.username  # Return the generated username
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#Login using Username & Password
class UserLoginView(APIView):
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
    
#Login using Phone Number & OTP
class SendOTP(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number')
        if not phone_number:
            return Response({"detail": "Phone number is required"}, status=status.HTTP_400_BAD_REQUEST)
        send_otp(phone_number)
        return Response({"detail": "OTP sent successfully"}, status=status.HTTP_200_OK)
    
class OTPLoginView(APIView):
    def post(self, request):
        serializer = OTPLoginSerializer(data=request.data)
        if serializer.is_valid():
            user=serializer.validated_data['user']
            refresh= RefreshToken.for_user(user)
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
            return Response(response_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

#Get User Details
class UserDetails(APIView):   
    def get(self, request):
        user = request.user
        if user.is_authenticated:
            user_data = {
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'role': user.role,
                
            }
            return Response(user_data, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "User not authenticated."}, status=status.HTTP_401_UNAUTHORIZED)


def get_captcha(request):
    hashkey = CaptchaStore.generate_key()
    imageurl = captcha_image_url(hashkey)
    response = JsonResponse({
        'key': hashkey,
        'image_url': imageurl
    })
    return response        


class DistrictAdd(APIView):
    def post(self, request, format=None):
        serializer = DistrictSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, id, format=None):
        district = District.objects.get(id=id)
        serializer = DistrictSerializer(
            district, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DistrictView(APIView):
    def get(self, request, pk=None, format=None):
        id = pk
        if id is not None:
            datas = District.objects.get(id=id)
            serializer = DistrictSerializer(datas)
            return Response(serializer.data)
        datas = District.objects.filter()
        serializer = DistrictSerializer(datas, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK) 

class SubdivisionView(APIView):
    def get(self, request, pk=None, format=None):
        if pk is not None:
            try:
                subdivision = Subdivision.objects.get(id=pk)
                serializer = SubDivisonSerializer(subdivision)
                return Response(serializer.data)
            except Subdivision.DoesNotExist:
                raise NotFound(detail="Subdivision not found", code=status.HTTP_404_NOT_FOUND)
        
        # If no pk, return all subdivisions
        subdivisions = Subdivision.objects.all()
        serializer = SubDivisonSerializer(subdivisions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK) 

class GetSubdivisionByDistrictCode(APIView):
    def get(self, request, district_code=None, format=None):
        if district_code is not None:
            subdivisions = Subdivision.objects.filter(DistrictCode__DistrictCode=district_code)
            
            if not subdivisions.exists():
                raise NotFound(detail="No subdivisions found for this district code", code=status.HTTP_404_NOT_FOUND)

            serializer = SubDivisonSerializer(subdivisions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        return Response({"detail": "District code is required"}, status=status.HTTP_400_BAD_REQUEST)        


class SubDivisonApi(APIView):
    def post(self, request, format=None):
        serializer = SubDivisonSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, pk=None, format=None):
        id = pk
        if id is not None:
            datas = Subdivision.objects.get(id=id)
            serializer = SubDivisonSerializer(datas)
            return Response(serializer.data)
        datas = Subdivision.objects.filter()
        serializer = SubDivisonSerializer(datas, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        subdivision = Subdivision.objects.get(id=id)
        serializer = SubDivisonSerializer(
            subdivision, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
