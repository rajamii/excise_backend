from rest_framework import serializers
from auth.user.models import CustomUser

from captcha.models import CaptchaStore
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    subdivision = serializers.SerializerMethodField()
    firstName = serializers.CharField(source='first_name', read_only=True)
    middleName = serializers.CharField(source='middle_name', read_only=True)
    lastName = serializers.CharField(source='last_name', read_only=True)
    phoneNumber = serializers.CharField(source='phone_number', read_only=True)
    
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'username', 'firstName', 'middleName', 'lastName', 
                 'phoneNumber', 'district', 'subdivision', 'address', 'role',
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
            'name': district.district,
            'code': district.district_code
        } if district else None

    def get_subdivision(self, obj):
        subdivision = obj.subdivision
        return {
            'name': subdivision.subdivision,
            'code': subdivision.subdivision_code
        } if subdivision else None

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
