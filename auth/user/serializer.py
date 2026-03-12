from rest_framework import serializers
from auth.user.models import CustomUser, LicenseeProfile, OICOfficerAssignment
from auth.roles.models import Role
from models.masters.core.models import District, Subdivision
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
    panNumber = serializers.SerializerMethodField()
    hasActiveLicense = serializers.SerializerMethodField()
    isActive = serializers.BooleanField(source='is_active', read_only=True)
    
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'username', 'firstName', 'middleName', 'lastName',
                 'phoneNumber', 'panNumber', 'district', 'subdivision', 'address', 'role',
                 'created_by', 'hasActiveLicense', 'isActive'
        ]
                 
        extra_kwargs = {
            'password': {'write_only': True},
            'username': {'read_only': True}
        }

    def get_role(self, obj):
        role = obj.role
        return {
            'id': role.id
        } if role else None
    
    def get_created_by(self, obj):
        return obj.created_by.role.id if obj.created_by and obj.created_by.role else None
    
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

    def get_hasActiveLicense(self, obj):
        # Check NewLicenseApplication (related_name='license_applications')
        if obj.license_applications.filter(current_stage__name='approved').exists():
            return True
        # Check LicenseApplication (related_name='new_license_applications')
        if obj.new_license_applications.filter(current_stage__name='approved').exists():
            return True
        return False

    def get_panNumber(self, obj):
        profile = getattr(obj, 'licensee_profile', None)
        return getattr(profile, 'pan_number', None)

class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'email', 'first_name', 'middle_name', 'last_name', 'phone_number',
            'district', 'subdivision', 'address', 'role', 'password', 'is_active'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        return CustomUser.objects.create_user(**validated_data)


class UserUpdateSerializer(serializers.ModelSerializer):
    # Accept frontend camelCase payload keys for updates
    firstName = serializers.CharField(source='first_name', required=False)
    middleName = serializers.CharField(source='middle_name', required=False, allow_blank=True)
    lastName = serializers.CharField(source='last_name', required=False)
    phoneNumber = serializers.CharField(source='phone_number', required=False)
    role = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(),
        required=False,
        allow_null=True
    )
    district = serializers.SlugRelatedField(
        slug_field='district_code',
        queryset=District.objects.all(),
        required=False
    )
    subdivision = serializers.SlugRelatedField(
        slug_field='subdivision_code',
        queryset=Subdivision.objects.all(),
        required=False
    )
    isActive = serializers.BooleanField(source='is_active', required=False)

    class Meta:
        model = CustomUser
        fields = [
            'email', 'firstName', 'middleName', 'lastName',
            'phoneNumber', 'district', 'subdivision', 'address', 'role', 'isActive'
        ]

    def to_internal_value(self, data):
        """
        Accept both primitive and object-shaped values from clients:
        - role: 2 or {"id": 2}
        - district: 11 or {"code": 11} or {"districtCode": 11}
        - subdivision: 101 or {"code": 101} or {"subdivisionCode": 101}
        - camelCase and snake_case keys (parser may convert to snake_case)
        Also ignore unsupported keys in update payloads.
        """
        allowed_keys = set(self.fields.keys())
        incoming = dict(data.items()) if hasattr(data, 'items') else dict(data)

        # DRF CamelCaseJSONParser can convert frontend camelCase payloads to snake_case.
        # Normalize common snake_case aliases back to serializer field names.
        aliases = {
            'first_name': 'firstName',
            'middle_name': 'middleName',
            'last_name': 'lastName',
            'phone_number': 'phoneNumber',
            'role_id': 'role',
            'is_active': 'isActive',
        }
        for source_key, target_key in aliases.items():
            if source_key in incoming and target_key not in incoming:
                incoming[target_key] = incoming.get(source_key)

        role_value = incoming.get('role')
        if isinstance(role_value, dict):
            incoming['role'] = role_value.get('id') if role_value.get('id') is not None else role_value.get('roleId')

        district_value = incoming.get('district')
        if isinstance(district_value, dict):
            incoming['district'] = (
                district_value.get('code')
                if district_value.get('code') is not None
                else (
                    district_value.get('districtCode')
                    if district_value.get('districtCode') is not None
                    else district_value.get('district_code')
                )
            )

        subdivision_value = incoming.get('subdivision')
        if isinstance(subdivision_value, dict):
            incoming['subdivision'] = (
                subdivision_value.get('code')
                if subdivision_value.get('code') is not None
                else (
                    subdivision_value.get('subdivisionCode')
                    if subdivision_value.get('subdivisionCode') is not None
                    else subdivision_value.get('subdivision_code')
                )
            )

        # Support top-level districtCode/subdivisionCode payload variants.
        if incoming.get('district') is None:
            if incoming.get('districtCode') is not None:
                incoming['district'] = incoming.get('districtCode')
            elif incoming.get('district_code') is not None:
                incoming['district'] = incoming.get('district_code')

        if incoming.get('subdivision') is None:
            if incoming.get('subdivisionCode') is not None:
                incoming['subdivision'] = incoming.get('subdivisionCode')
            elif incoming.get('subdivision_code') is not None:
                incoming['subdivision'] = incoming.get('subdivision_code')

        filtered = {k: v for k, v in incoming.items() if k in allowed_keys}
        return super().to_internal_value(filtered)
    
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

        existing_user = CustomUser.objects.filter(username=username).first()
        if existing_user and not existing_user.is_active:
            raise serializers.ValidationError("Your account is inactive. Contact administrator for login.")

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

class LicenseeSignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    pan_number = serializers.CharField(max_length=10)
    address= serializers.CharField(max_length=255)
    class Meta:
        model = CustomUser
        fields = [
            'email', 'first_name', 'middle_name', 'last_name', 'phone_number',
            'district', 'subdivision', 'address', 'pan_number', 'password'
        ]

    def validate_phone_number(self, value):
        if CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return value

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value
    
    def create(self, validated_data):
        # Extract licensee-specific data BEFORE creating the user
        pan_number = validated_data.pop('pan_number')

        # Get Licensee role
        try:
            licensee_role = Role.objects.get(name__iexact="licensee")
        except Role.DoesNotExist:
            raise serializers.ValidationError("Licensee role not configured. Contact support.")

        # Create the user — do NOT pass pan_number or address here!
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            middle_name=validated_data.get('middle_name', ''),
            last_name=validated_data['last_name'],
            phone_number=validated_data['phone_number'],
            district=validated_data.get('district'),
            subdivision=validated_data.get('subdivision'),
            address=validated_data['address'],
            password=validated_data['password'],
            role=licensee_role,
            created_by=None  # Self-registered
        )

        # Now create the LicenseeProfile with the extracted data
        LicenseeProfile.objects.create(
            user=user,
            pan_number=pan_number
        )

        return user


class OICApprovedEstablishmentSerializer(serializers.Serializer):
    applicationId = serializers.CharField()
    establishmentName = serializers.CharField()
    licenseId = serializers.CharField()
    licenseeId = serializers.CharField()
    districtCode = serializers.CharField(allow_blank=True)
    subdivisionCode = serializers.CharField(allow_blank=True)


class OICOfficerCreateSerializer(serializers.Serializer):
    # Incoming JSON is camelCase from frontend, but CamelCaseJSONParser
    # converts request keys to snake_case before serializer validation.
    approved_application_id = serializers.CharField()
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=10)

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def validate_phone_number(self, value):
        if CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return value


class OICOfficerUpdateSerializer(serializers.Serializer):
    approved_application_id = serializers.CharField()
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=10)

    def validate(self, attrs):
        officer = self.context.get('officer')
        if officer is None:
            raise serializers.ValidationError("Officer context is required.")

        email = attrs.get('email')
        phone_number = attrs.get('phone_number')

        if CustomUser.objects.exclude(pk=officer.pk).filter(email=email).exists():
            raise serializers.ValidationError({'email': ["This email is already registered."]})

        if CustomUser.objects.exclude(pk=officer.pk).filter(phone_number=phone_number).exists():
            raise serializers.ValidationError({'phone_number': ["This phone number is already registered."]})

        return attrs


class OICOfficerAssignmentSerializer(serializers.ModelSerializer):
    officerId = serializers.IntegerField(source='officer.id', read_only=True)
    username = serializers.CharField(source='officer.username', read_only=True)
    name = serializers.SerializerMethodField()
    email = serializers.CharField(source='officer.email', read_only=True)
    phoneNumber = serializers.CharField(source='officer.phone_number', read_only=True)
    applicationId = serializers.CharField(source='approved_application.application_id', read_only=True)
    licenseId = serializers.CharField(source='license.license_id', read_only=True)
    officer_created_at = serializers.DateTimeField(source='officer.date_joined', read_only=True)
    isActive = serializers.BooleanField(source='officer.is_active', read_only=True)

    class Meta:
        model = OICOfficerAssignment
        fields = [
            'id',
            'officerId',
            'username',
            'name',
            'email',
            'phoneNumber',
            'applicationId',
            'licenseId',
            'licensee_id',
            'establishment_name',
            'created_at',
            'officer_created_at',
            'isActive',
        ]

    def get_name(self, obj):
        first_name = str(getattr(obj.officer, 'first_name', '') or '').strip()
        last_name = str(getattr(obj.officer, 'last_name', '') or '').strip()
        return f"{first_name} {last_name}".strip()

       
