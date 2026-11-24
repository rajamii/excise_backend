from rest_framework import serializers
from models.masters.core.models import District

class DistrictSerializer(serializers.ModelSerializer):
    # Computed fields
    status = serializers.SerializerMethodField()
    state = serializers.CharField(source='state_code.state', read_only=True)
    district_name = serializers.CharField(source='district', read_only=True)
    districtCode = serializers.IntegerField(source='district_code', read_only=True)
    site_enquiry_officers_count = serializers.SerializerMethodField()
    officers_count = serializers.SerializerMethodField()
    site_enquiry_officers = serializers.SerializerMethodField()
    officers = serializers.SerializerMethodField()

    class Meta:
        model = District
        fields = [
            'id',
            'district',
            'district_name',
            'district_code',
            'districtCode',
            'state_code',
            'state',
            'is_active',
            'status',
            'multiple_site_enquiry',
            'site_enquiry_officers_count',
            'officers_count',
            'site_enquiry_officers',
            'officers',
        ]
        extra_kwargs = {
            'district_code': {
                'validators': []
            }
        }

    def validate_district_code(self, value):
        """Ensure district code is unique per state"""
        queryset = District.objects.filter(district_code=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("District code must be unique")
        return value

    def update(self, instance, validated_data):
        multiple = validated_data.get('multiple_site_enquiry')
        instance = super().update(instance, validated_data)
        if multiple is not None:
            from models.masters.core.models import SiteEnquiryStageConfig
            SiteEnquiryStageConfig.objects.update_or_create(
                district=instance,
                defaults={'multiple_site_enquiry': multiple}
            )
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        cfg = getattr(instance, 'site_enquiry_stage_config', None)
        if cfg:
            data['multiple_site_enquiry'] = bool(cfg.multiple_site_enquiry)
        return data

    def get_status(self, obj):
        return 'Active' if obj.is_active else 'Inactive'

    def get_site_enquiry_officers_count(self, obj):
        from auth.user.models import CustomUser
        return CustomUser.objects.filter(
            district__district_code=obj.district_code,
            role__name__icontains='site inq',
            is_active=True
        ).count()

    def get_officers_count(self, obj):
        return self.get_site_enquiry_officers_count(obj)

    def get_site_enquiry_officers(self, obj):
        from auth.user.models import CustomUser
        officers = CustomUser.objects.filter(
            district__district_code=obj.district_code,
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
                'district_name': obj.district,
                'district_code': obj.district_code,
            }
            for u in officers
        ]

    def get_officers(self, obj):
        return self.get_site_enquiry_officers(obj)
