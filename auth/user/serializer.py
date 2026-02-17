from rest_framework import serializers
from django.utils import timezone
from auth.user.models import CustomUser, LicenseeProfile
from auth.roles.models import Role
from models.masters.core.models import District, Subdivision
from captcha.models import CaptchaStore
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

# Fields that are set once at creation and must never change afterwards
IMMUTABLE_PROFILE_FIELDS = ('father_name', 'dob', 'gender', 'nationality', 'pan_number')


# ─────────────────────────────────────────────────────────────────────────────
# User serializers
# ─────────────────────────────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    subdivision = serializers.SerializerMethodField()
    firstName = serializers.CharField(source='first_name', read_only=True)
    middleName = serializers.CharField(source='middle_name', read_only=True)
    lastName = serializers.CharField(source='last_name', read_only=True)
    phoneNumber = serializers.CharField(source='phone_number', read_only=True)
    hasActiveLicense = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id', 'email', 'username', 'firstName', 'middleName', 'lastName',
            'phoneNumber', 'district', 'subdivision', 'address', 'role',
            'created_by', 'hasActiveLicense'
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'username': {'read_only': True}
        }

    def get_role(self, obj):
        role = obj.role
        return {'id': role.id} if role else None

    def get_created_by(self, obj):
        return obj.created_by.role.id if obj.created_by and obj.created_by.role else None

    def get_district(self, obj):
        district = obj.district
        return {'name': district.district, 'code': district.district_code} if district else None

    def get_subdivision(self, obj):
        subdivision = obj.subdivision
        return {'name': subdivision.subdivision, 'code': subdivision.subdivision_code} if subdivision else None

    def get_hasActiveLicense(self, obj):
        if obj.license_applications.filter(current_stage__name='approved').exists():
            return True
        if obj.new_license_applications.filter(current_stage__name='approved').exists():
            return True
        return False


class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'email', 'first_name', 'middle_name', 'last_name', 'phone_number',
            'district', 'subdivision', 'address', 'role', 'password'
        ]
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return CustomUser.objects.create_user(**validated_data)


class UserUpdateSerializer(serializers.ModelSerializer):
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

    class Meta:
        model = CustomUser
        fields = [
            'email', 'firstName', 'middleName', 'lastName',
            'phoneNumber', 'district', 'subdivision', 'address', 'role'
        ]

    def to_internal_value(self, data):
        """Accept both primitive and object-shaped FK values from clients."""
        allowed_keys = set(self.fields.keys())
        incoming = dict(data.items()) if hasattr(data, 'items') else dict(data)

        role_value = incoming.get('role')
        if isinstance(role_value, dict):
            incoming['role'] = role_value.get('id')

        district_value = incoming.get('district')
        if isinstance(district_value, dict):
            incoming['district'] = (
                district_value.get('code')
                if district_value.get('code') is not None
                else district_value.get('districtCode')
            )

        subdivision_value = incoming.get('subdivision')
        if isinstance(subdivision_value, dict):
            incoming['subdivision'] = (
                subdivision_value.get('code')
                if subdivision_value.get('code') is not None
                else subdivision_value.get('subdivisionCode')
            )

        filtered = {k: v for k, v in incoming.items() if k in allowed_keys}
        return super().to_internal_value(filtered)


# ─────────────────────────────────────────────────────────────────────────────
# Auth serializers
# ─────────────────────────────────────────────────────────────────────────────

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

        try:
            captcha_store = CaptchaStore.objects.get(hashkey=hashkey)
            if captcha_store.response.strip().lower() != response.strip().lower():
                raise serializers.ValidationError("Invalid captcha.")
            captcha_store.delete()
        except CaptchaStore.DoesNotExist:
            raise serializers.ValidationError("Invalid captcha.")

        refresh = RefreshToken.for_user(user)
        return {
            'username': user.username,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }


# ─────────────────────────────────────────────────────────────────────────────
# LicenseeProfile serializers
# ─────────────────────────────────────────────────────────────────────────────

class LicenseeProfileSerializer(serializers.ModelSerializer):
    """
    Read / partial-update serializer for an existing LicenseeProfile.
    Immutable fields (pan_number, father_name, dob, gender, nationality) are
    locked after creation and cannot be changed via PATCH or PUT.
    """

    # ── Display fields ────────────────────────────────────────────
    gender_display = serializers.CharField(
        source='get_gender_display', read_only=True
    )
    marital_status_display = serializers.CharField(
        source='get_marital_status_display', read_only=True
    )
    residential_status_display = serializers.CharField(
        source='get_residential_status_display', read_only=True
    )
    created_by_username = serializers.CharField(
        source='created_by.username', read_only=True
    )

    class Meta:
        model = LicenseeProfile
        fields = [
            'id',
            'user',
            'pan_number',
            'father_name',
            'dob',
            'gender',
            'gender_display',
            'nationality',
            'marital_status',
            'marital_status_display',
            'residential_status',
            'residential_status_display',
            'created_by',
            'created_by_username',
            'operation_date',
        ]
        read_only_fields = ['id', 'user', 'operation_date', 'created_by']

    # ── Field-level validation ────────────────────────────────────

    def validate_dob(self, value):
        if value >= timezone.now().date():
            raise serializers.ValidationError("Date of birth must be a past date.")
        return value

    def validate_father_name(self, value):
        return ' '.join(value.strip().split())

    # ── Object-level validation ───────────────────────────────────

    def validate(self, data):
        """Block changes to immutable fields on update (PUT or PATCH)."""
        if self.instance is not None:
            attempted_changes = [
                field for field in IMMUTABLE_PROFILE_FIELDS
                if field in data and str(getattr(self.instance, field)) != str(data[field])
            ]
            if attempted_changes:
                raise serializers.ValidationError({
                    field: f"'{field}' cannot be changed after the profile is created."
                    for field in attempted_changes
                })
        return data

    # ── Custom save logic ─────────────────────────────────────────

    def update(self, instance, validated_data):
        # Safety net: strip immutable fields even if validation somehow passed
        for field in IMMUTABLE_PROFILE_FIELDS:
            validated_data.pop(field, None)
        return super().update(instance, validated_data)


class LicenseeSignupSerializer(serializers.ModelSerializer):
    """
    Used for self-registration of a licensee user.
    Creates both the CustomUser and the linked LicenseeProfile atomically.
    """
    password = serializers.CharField(write_only=True, min_length=8)

    # LicenseeProfile fields — collected at signup
    pan_number = serializers.CharField(max_length=10)
    father_name = serializers.CharField(max_length=100)
    dob = serializers.DateField()
    gender = serializers.ChoiceField(choices=['M', 'F', 'O'])
    nationality = serializers.CharField(max_length=50)
    marital_status = serializers.ChoiceField(
        choices=['SINGLE', 'MARRIED', 'DIVORCED', 'WIDOWED'],
        required=False,
        allow_blank=True
    )
    residential_status = serializers.ChoiceField(
        choices=['RESIDENT', 'NON_RESIDENT', 'OCI'],
        required=False,
        allow_blank=True
    )

    class Meta:
        model = CustomUser
        fields = [
            # User fields
            'email', 'first_name', 'middle_name', 'last_name',
            'phone_number', 'district', 'subdivision', 'address', 'password',
            # Profile fields
            'pan_number', 'father_name', 'dob', 'gender', 'nationality',
            'marital_status', 'residential_status',
        ]

    # ── Field-level validation ────────────────────────────────────

    def validate_phone_number(self, value):
        if CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return value

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def validate_dob(self, value):
        if value >= timezone.now().date():
            raise serializers.ValidationError("Date of birth must be a past date.")
        return value

    def validate_father_name(self, value):
        return ' '.join(value.strip().split())

    # ── Create ────────────────────────────────────────────────────

    def create(self, validated_data):
        # Extract profile-only fields before creating the user
        profile_fields = {
            'pan_number':         validated_data.pop('pan_number'),
            'father_name':        validated_data.pop('father_name'),
            'dob':                validated_data.pop('dob'),
            'gender':             validated_data.pop('gender'),
            'nationality':        validated_data.pop('nationality'),
            'marital_status':     validated_data.pop('marital_status', ''),
            'residential_status': validated_data.pop('residential_status', ''),
        }

        # Resolve the Licensee role
        try:
            from auth.roles.models import Role
            licensee_role = Role.objects.get(name__iexact="licensee")
        except Role.DoesNotExist:
            raise serializers.ValidationError(
                "Licensee role not configured. Contact support."
            )

        # Create the user
        user = CustomUser.objects.create_user(
            **validated_data,
            role=licensee_role,
            created_by=None  # Self-registered
        )

        # Create the linked profile
        LicenseeProfile.objects.create(
            user=user,
            created_by=None,
            **profile_fields
        )

        return user