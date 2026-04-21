from rest_framework import serializers

from .models import BrandOwner, BrandOwnerFee, BrandOwnerType, LiquorBrand, LiquorKind


def _category_label(code):
    return f"Category {code}" if code is not None else ""


def _type_label(code):
    return f"Type {code}" if code is not None else ""


class BrandOwnerTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandOwnerType
        fields = ['brand_owner_type_code', 'brand_owner_type_desc']


class BrandOwnerSerializer(serializers.ModelSerializer):
    brand_owner_type_desc = serializers.CharField(
        source='brand_owner_type.brand_owner_type_desc', read_only=True
    )

    class Meta:
        model = BrandOwner
        fields = [
            'brand_owner_code',
            'brand_owner_type',
            'brand_owner_type_desc',
            'brand_owner_name',
            'brand_owner_mobile_no',
            'brand_owner_company_address',
            'brand_owner_address',
            'brand_owner_pincode',
            'brand_owner_pan',
            'brand_owner_email',
            'brand_owner_origin',
            'brand_owner_country',
            'brand_owner_state',
            'liquor_bowner_code',
            'brand_owner_licensee_id_no',
            'parent_licensee_id_no',
            'renewed_upto',
            'enable_status',
            'opr_date',
            'user_id',
        ]
        read_only_fields = ['opr_date']


class LiquorCategorySerializer(serializers.Serializer):
    liquor_cat_code = serializers.IntegerField()
    liquor_cat_desc = serializers.CharField()
    liquor_cat_abbr = serializers.CharField()
    delete_status = serializers.CharField()


class LiquorKindSerializer(serializers.ModelSerializer):
    liquor_cat_desc = serializers.SerializerMethodField()

    def get_liquor_cat_desc(self, obj):
        return _category_label(getattr(obj, 'liquor_cat', None))

    class Meta:
        model = LiquorKind
        fields = [
            'id',
            'liquor_cat',
            'liquor_cat_desc',
            'liquor_kind_code',
            'liquor_kind_desc',
            'liquor_kind_abbr',
            'delete_status',
        ]


class LiquorTypeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    liquor_cat = serializers.IntegerField()
    liquor_kind = serializers.IntegerField()
    liquor_type_code = serializers.IntegerField()
    liquor_type_desc = serializers.CharField()
    delete_status = serializers.CharField()


class LiquorBrandSerializer(serializers.ModelSerializer):
    liquor_cat_desc  = serializers.SerializerMethodField()
    liquor_kind_desc = serializers.CharField(source='liquor_kind.liquor_kind_desc', read_only=True)
    liquor_kind_abbr = serializers.CharField(source='liquor_kind.liquor_kind_abbr', read_only=True)
    liquor_type_desc = serializers.SerializerMethodField()

    def get_liquor_cat_desc(self, obj):
        return _category_label(getattr(obj, 'liquor_cat', None))

    def get_liquor_type_desc(self, obj):
        return _type_label(getattr(obj, 'liquor_type', None))

    class Meta:
        model = LiquorBrand
        fields = [
            'liquor_brand_code',
            'liquor_cat',
            'liquor_cat_desc',
            'liquor_kind',
            'liquor_kind_desc',
            'liquor_kind_abbr',
            'liquor_type',
            'liquor_type_desc',
            'liquor_brand_desc',
            'brand_name_alias',
            'liquor_type_code_old',
            'entry_flag',
            'delete_status',
        ]


class BrandOwnerFeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandOwnerFee
        fields = [
            'id',
            'registration_fee',
            'collaboration_fees',
            'security_deposit',
            'active_status',
            'from_date',
            'to_date',
            'user_id',
            'opr_date',
        ]
        read_only_fields = ['opr_date']
