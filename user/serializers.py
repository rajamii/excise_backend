from rest_framework import serializers
from .models import CustomUser
from django.contrib.auth.password_validation import validate_password
from captcha.models import CaptchaStore
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from roles.models import Role

# --- User Registration & Login Serializers ---

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True, required=True)
    middle_name = serializers.CharField(required=False, allow_blank=True) # middle name is optional
    
    class Meta:
        model = CustomUser
        fields = [
            'email', 'password', 'confirm_password', 'role_id', 
            'first_name', 'middle_name', 'last_name', 'phone_number', 
            'district', 'subdivision', 'address', 'created_by', 
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'confirm_password': {'write_only': True}
        }

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email is already in use.")
        return value
    
    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password', None)
        user = CustomUser.objects.create_user(**validated_data)
        return user

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

        if not username or not password or not hashkey or not response:
            raise serializers.ValidationError("All fields are required.")

        user = authenticate(username=username, password=password)
        if not user:
            raise serializers.ValidationError("Invalid login credentials.")
        if not user.is_active:
            raise serializers.ValidationError("User account is inactive.")

        try:
            captcha_store = CaptchaStore.objects.get(hashkey=hashkey)
            if captcha_store.response.strip().lower() != response.strip().lower():
                raise serializers.ValidationError("Invalid captcha.")
            captcha_store.delete()
        except CaptchaStore.DoesNotExist:
            raise serializers.ValidationError("Invalid captcha.")

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        return {
            'username': user.username,
            'access': access_token,
            'refresh': refresh_token,
        }
    
class UserUpdateSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(
        slug_field='name',
        queryset=Role.objects.all(),
        required=False
    )

    class Meta:
        model = CustomUser
        fields = [
            'first_name',
            'middle_name',
            'last_name',
            'email',
            'phone_number',
            'district',
            'subdivision',
            'address',
            'role',
        ]
        extra_kwargs = {
            'email': {'required': False},
            'phone_number': {'required': False},
        }

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

# --- Salesman/Barman & Documents Serializers ---

# class DocumentsDetailsSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = DocumentsDetails
#         fields = [
#             'id', 'passport_size_photo', 'aadhar_card', 'sikkim_subject_certificate', 'date_of_birth_proof'
#         ]

# class SalesmanBarmanDetailsSerializer(serializers.ModelSerializer):
#     documents = DocumentsDetailsSerializer()

#     class Meta:
#         model = SalesmanBarmanDetails
#         fields = [
#             'id', 'first_name', 'middle_name', 'last_name', 'father_or_husband_name', 'gender', 'nationality',
#             'address', 'pan_number', 'aadhar_number', 'email', 'mode_of_operation', 'application_year', 
#             'application_id', 'application_date', 'district', 'license_category', 'license_type', 
#             'salesman_specific_field', 'barman_specific_field', 'documents'
#         ]
    
    # def create(self, validated_data):
    #     documents_data = validated_data.pop('documents')
    #     document_instance = DocumentsDetails.objects.create(**documents_data)
    #     salesman_barman_instance = SalesmanBarmanDetails.objects.create(**validated_data)
    #     salesman_barman_instance.documents = document_instance
    #     salesman_barman_instance.save()
    #     return salesman_barman_instance

    # def update(self, instance, validated_data):
    #     documents_data = validated_data.pop('documents', None)
    #     for attr, value in validated_data.items():
    #         setattr(instance, attr, value)
    #     if documents_data:
    #         for attr, value in documents_data.items():
    #             setattr(instance.documents, attr, value)
    #         instance.documents.save()
    #     instance.save()
    #     return instance
