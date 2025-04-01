# from rest_framework import serializers
# from .models import *
# from django.contrib.auth import authenticate
# from django.contrib.auth.password_validation import validate_password
# from django.core.exceptions import ValidationError
# from captcha.models import CaptchaStore
# from rest_framework_simplejwt.tokens import RefreshToken
# from otp.views import verify_otp


# # class UserRegistrationSerializer(serializers.ModelSerializer):
# #     password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
# #     confirm_password = serializers.CharField(write_only=True, required=True)
    
# #     class Meta:
# #         model = CustomUser
# #         fields = [
# #             'email', 'password', 'confirm_password', 'role', 
# #             'first_name', 'middle_name', 'last_name', 'phonenumber', 
# #             'district', 'subdivision', 'address', 'created_by', 
# #         ]
    
# #     def validate(self, data):
# #         # Confirm that password and confirm_password match
# #         if data['password'] != data['confirm_password']:
# #             raise serializers.ValidationError({"password": "Passwords do not match."})
# #         return data

# #     def create(self, validated_data):
# #         validated_data.pop('confirm_password', None)  # Remove confirm_password from validated_data
        
# #         # Call create_user method to handle username generation and user creation
# #         user = CustomUser.objects.create_user(**validated_data)
# #         return user

        
# # class LoginSerializer(serializers.Serializer):
# #     username = serializers.CharField(max_length=255)
# #     password = serializers.CharField(write_only=True)
# #     hashkey = serializers.CharField()
# #     response = serializers.CharField()

# #     def validate(self, data):
# #         username = data.get('username')
# #         password = data.get('password')
# #         hashkey = data.get('hashkey')
# #         response = data.get('response')

# #         # Validate required fields
# #         if not username or not password or not hashkey or not response:
# #             raise serializers.ValidationError("All fields are required.")

# #         # Authenticate user
# #         user = authenticate(username=username, password=password)
# #         if not user:
# #             raise serializers.ValidationError("Invalid login credentials.")

# #         # Validate captcha
# #         try:
# #             CaptchaStore.objects.get(hashkey=hashkey, response=response.strip().lower())
# #         except CaptchaStore.DoesNotExist:
# #             raise serializers.ValidationError("Invalid captcha.")

# #         # Generate JWT tokens
# #         refresh = RefreshToken.for_user(user)
# #         access_token = str(refresh.access_token)
# #         refresh_token = str(refresh)


# #         # Return validated data with tokens
# #         return {
# #             'username': user.username,
# #             'access': access_token,
# #             'refresh': refresh_token,
# #         }
# # #UserList Serializer
# # class UserListSerializer(serializers.ModelSerializer):
# #     class Meta:
# #         model = CustomUser
# #         fields = ['id', 'username', 'email', 'role', 'first_name', 'last_name', 'phonenumber', 'district', 'subdivision', 'address', 'created_by']


# # class DistrictSerializer(serializers.ModelSerializer):
# #     stateName = serializers.CharField(source='StateCode.State', read_only=True)
# #     class Meta: 
# #         model= District
# #         fields = '__all__'

# # #SubDividionSerializer
# # class SubDivisonSerializer(serializers.ModelSerializer):
# #     District = serializers.CharField(source='DistrictCode.District', read_only=True)

# #     class Meta: 
# #         model= Subdivision
# #         fields = '__all__'        
