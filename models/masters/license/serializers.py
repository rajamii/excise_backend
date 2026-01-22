from rest_framework import serializers
from .models import License
from auth.user.models import CustomUser


class LicenseSerializer(serializers.ModelSerializer):
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    excise_district_name = serializers.CharField(source='excise_district.district', read_only=True)
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)

    class Meta:
        model = License
        fields = [
            'license_id',
            'source_type',
            'source_type_display',
            'license_category',
            'license_category_name',
            'excise_district',
            'excise_district_name',
            'issue_date',
            'valid_up_to',
            'is_active',
            'print_count',
            'is_print_fee_paid',
        ]


class LicenseDetailSerializer(serializers.ModelSerializer):
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    excise_district_name = serializers.CharField(source='excise_district.district', read_only=True)
    issue_date = serializers.DateField(format="%d/%m/%Y")
    valid_up_to = serializers.DateField(format="%d/%m/%Y")

    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    source_application_id = serializers.CharField(source='source_application.application_id', read_only=True)

    application_data = serializers.SerializerMethodField()

    class Meta:
        model = License
        fields = [
            'license_id',
            'source_type_display',
            'source_application_id',
            'license_category_name',
            'excise_district_name',
            'issue_date',
            'valid_up_to',
            'is_active',
            'print_count',
            'is_print_fee_paid',
            'application_data',
        ]

    def get_application_data(self, obj):
        source = obj.source_application
        if not source:
            return {}

        # NEW LICENSE APPLICATION (NA)
        if obj.source_type == 'new_license_application':
            return {
                "applicant_name": source.applicant_name,
                "father_husband_name": source.father_husband_name,
                "dob": source.dob,
                "gender": source.get_gender_display() if hasattr(source, 'get_gender_display') else source.gender,
                "mobile_number": source.mobile_number,
                "email": source.email,
                "pan": source.pan,
                "address": source.present_address,
                "establishment_name": source.establishment_name,
                "site_district": source.site_district.district,
                "site_subdivision": source.site_subdivision.subdivision,
                "police_station": source.police_station.police_station,
                "license_type": source.license_type.license_type,
                "license_sub_category": source.license_sub_category.description,
                "mode_of_operation": source.get_mode_of_operation_display(),
            }

        # RENEWAL / EXISTING LICENSE (LA)
        elif obj.source_type == 'license_application':
            # Use the actual field names from your LicenseApplication model
            return {
                "establishment_name": source.establishment_name,
                "licensee_name": source.establishment_name,  # often same
                "mobile_number": source.mobile_number,
                "email": source.email,
                "license_no": source.license_no,
                "initial_grant_date": source.initial_grant_date,
                "business_address": source.business_address or source.site_address,
                "police_station": source.police_station.police_station if source.police_station else None,
                "license_nature": source.license_nature,
                "functioning_status": source.functioning_status,
                "yearly_license_fee": source.yearly_license_fee,
                "license_type": source.license_type.license_type if hasattr(source, 'license_type') else None,
            }

        # SALESMAN / BARMAN (SB)
        elif obj.source_type == 'salesman_barman':
            full_name = " ".join(filter(None, [
                source.firstName,
                source.middleName or "",
                source.lastName
            ])).strip()

            return {
                "role": source.get_role_display(),
                "name": full_name,
                "father_husband_name": source.fatherHusbandName,
                "dob": source.dob,
                "gender": source.get_gender_display(),
                "address": source.address,
                "mobile_number": source.mobileNumber,
                "email": source.emailId or "",
                "pan": source.pan,
                "aadhaar": source.aadhaar,
                "sikkim_subject": source.sikkimSubject,
                "attached_license": source.license.license_id,
            }

        return {}

class MyLicenseDetailsSerializer(serializers.ModelSerializer):

    first_name = serializers.CharField(source='source_application.applicant.first_name', read_only=True)
    middle_name = serializers.CharField(source='source_application.applicant.middle_name', read_only=True)
    last_name = serializers.CharField(source='source_application.applicant.last_name', read_only=True)
    username = serializers.CharField(source='source_application.applicant.username', read_only=True)
    email = serializers.CharField(source='source_application.applicant.email', read_only=True)
    phone_number = serializers.CharField(source='source_application.applicant.phone_number', read_only=True)
    role = serializers.CharField(source='source_application.applicant.role', read_only=True)
    district = serializers.CharField(source='source_application.applicant.district.district', read_only=True)
    
    application_type = serializers.CharField(source='get_source_type_display', read_only=True)
    license_category = serializers.CharField(source='license_category.license_category', read_only=True)
    license_sub_category = serializers.CharField(source='source_application.license_sub_category.description', read_only=True)
    establishment_name = serializers.CharField(source='source_application.establishment_name', read_only=True)
    site_district = serializers.CharField(source='excise_district.district', read_only=True)

    class Meta:
        model = License
        fields = [
            'license_id',
            'first_name',
            'middle_name',
            'last_name',
            'username',
            'email',
            'phone_number',
            'role',
            'district',
            'application_type',
            'license_category',
            'license_sub_category',
            'establishment_name',
            'site_district',
        ]