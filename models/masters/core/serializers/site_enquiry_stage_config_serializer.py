from rest_framework import serializers
from models.masters.core.models import SiteEnquiryStageConfig, District
from auth.user.models import CustomUser

class SiteEnquiryStageConfigSerializer(serializers.ModelSerializer):
    district_id = serializers.IntegerField(source='district.id', read_only=True)
    district_name = serializers.CharField(source='district.district', read_only=True)
    district = serializers.CharField(source='district.district', read_only=True)
    district_code = serializers.IntegerField(source='district.district_code', read_only=True)
    districtCode = serializers.IntegerField(source='district.district_code', read_only=True)
    officers_count = serializers.SerializerMethodField()
    site_enquiry_officers_count = serializers.SerializerMethodField()
    officers = serializers.SerializerMethodField()
    site_enquiry_officers = serializers.SerializerMethodField()

    class Meta:
        model = SiteEnquiryStageConfig
        fields = [
            'id',
            'district_id',
            'district',
            'district_name',
            'district_code',
            'districtCode',
            'multiple_site_enquiry',
            'is_active',
            'officers_count',
            'site_enquiry_officers_count',
            'officers',
            'site_enquiry_officers',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'district_id', 'district', 'district_name', 'district_code', 'districtCode', 'created_at', 'updated_at']

    def get_officers_count(self, obj):
        return CustomUser.objects.filter(
            district__district_code=obj.district.district_code,
            role__name__icontains='site inq',
            is_active=True
        ).count()

    def get_site_enquiry_officers_count(self, obj):
        return self.get_officers_count(obj)

    def get_officers(self, obj):
        officers = CustomUser.objects.filter(
            district__district_code=obj.district.district_code,
            role__name__icontains='site inq',
            is_active=True
        ).order_by('first_name', 'last_name')
        return [
            {
                'id': u.id,
                'username': u.username,
                'name': f"{u.first_name} {u.last_name}".strip(),
                'first_name': u.first_name,
                'last_name': u.last_name,
                'email': u.email,
                'phone_number': u.phone_number,
                'district_name': obj.district.district,
                'district_code': obj.district.district_code,
            }
            for u in officers
        ]

    def get_site_enquiry_officers(self, obj):
        return self.get_officers(obj)
