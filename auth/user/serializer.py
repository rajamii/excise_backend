from rest_framework import serializers
from auth.user.models import CustomUser

from captcha.models import CaptchaStore
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from models.masters.core.models import District, Subdivision
from ..roles.models import Role

class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    subdivision = serializers.SerializerMethodField()
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'username', 'first_name', 'middle_name', 'last_name', 
                 'phone_number', 'district', 'subdivision', 'address', 'role',
                 'created_by'
        ]
                 
        extra_kwargs = {
            'password': {'write_only': True},
            'username': {'read_only': True}
        }

    def get_role(self, obj):
        role = obj.role
        return {
            'id': role.id,
            'name': role.name
        } if role else None
    
    def get_created_by(self, obj):
        return obj.created_by.role.name if obj.created_by else None
    
    def get_district(self, obj):
        district = obj.district
        return {
            'district': district.district,
            'district_code': district.district_code
        } if district else None

    def get_subdivision(self, obj):
        subdivision = obj.subdivision
        return {
            'subdivision': subdivision.subdivision,
            'subdivision_code': subdivision.subdivision_code
        } if subdivision else None
    
    def update(self, instance, validated_data):
        # The request object is available in the context passed by the view
        request_data = self.context['request'].data

        # Manually handle nested foreign key updates
        
        # Look in request_data because SerializerMethodFields are read-only
        # and won't appear in validated_data.

        # Handle District
        district_data = request_data.get('district')
        if district_data and isinstance(district_data, dict):
            district_code = district_data.get('district_code')
            if district_code:
                instance.district = District.objects.get(district_code=district_code)

        # Handle Subdivision
        subdivision_data = request_data.get('subdivision')
        if subdivision_data and isinstance(subdivision_data, dict):
            subdivision_code = subdivision_data.get('subdivision_code')
            if subdivision_code:
                instance.subdivision = Subdivision.objects.get(subdivision_code=subdivision_code)

        # Handle Role
        role_data = request_data.get('role')
        if role_data and isinstance(role_data, dict):
            role_id = role_data.get('id')
            if role_id:
                instance.role = Role.objects.get(id=role_id)

        # Update all other fields from validated_data and save the instance
        # The super().update() method handles regular fields like first_name, etc.
        return super().update(instance, validated_data)

class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'email', 'first_name', 'middle_name', 'last_name', 'phone_number',
            'district', 'subdivision', 'address', 'role', 'password'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        return CustomUser.objects.create_user(**validated_data)
    
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=255)
    password = serializers.CharField(write_only=True)
    hashkey = serializers.CharField()
    response = serializers.CharField()

    def validate(self, data):
        username = data.get('username') 
        password = data.get('password')
        hashkey = data.get('hashkey')
        response = data.get('response')

        # Validate required fields
        if not username or not password or not hashkey or not response:
            raise serializers.ValidationError("All fields are required.")

        # Authenticate user
        user = authenticate(username=username, password=password)
        if not user:
            raise serializers.ValidationError("Invalid login credentials.")

        # Validate captcha
        try:
            captcha_store = CaptchaStore.objects.get(hashkey=hashkey)
            if captcha_store.response.strip().lower() != response.strip().lower():
               raise serializers.ValidationError("Invalid captcha.")
            captcha_store.delete() # delete the captcha after it is validated.
        except CaptchaStore.DoesNotExist:
            print("exception : captcha not found ")
            raise serializers.ValidationError("Invalid captcha.")

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)


        # Return validated data with tokens
        return {
            'username': user.username,
            'access': access_token,
            'refresh': refresh_token,
        }
