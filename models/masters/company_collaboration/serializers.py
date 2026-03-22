from rest_framework import serializers

from .models import BrandOwner, BrandOwnerFee, BrandOwnerType, LiquorBrand, LiquorCategory, LiquorKind, LiquorType


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


class LiquorCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = LiquorCategory
        fields = ['liquor_cat_code', 'liquor_cat_desc', 'liquor_cat_abbr', 'delete_status']


class LiquorKindSerializer(serializers.ModelSerializer):
    liquor_cat_desc = serializers.CharField(source='liquor_cat.liquor_cat_desc', read_only=True)

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


class LiquorTypeSerializer(serializers.ModelSerializer):
    liquor_cat_desc  = serializers.CharField(source='liquor_cat.liquor_cat_desc',   read_only=True)
    liquor_kind_desc = serializers.CharField(source='liquor_kind.liquor_kind_desc', read_only=True)

    class Meta:
        model = LiquorType
        fields = [
            'id',
            'liquor_cat',
            'liquor_cat_desc',
            'liquor_kind',
            'liquor_kind_desc',
            'liquor_type_code',
            'liquor_type_desc',
            'liquor_type_code_old',
            'delete_status',
        ]


class LiquorBrandSerializer(serializers.ModelSerializer):
    liquor_cat_desc  = serializers.CharField(source='liquor_cat.liquor_cat_desc',   read_only=True)
    liquor_kind_desc = serializers.CharField(source='liquor_kind.liquor_kind_desc', read_only=True)
    liquor_kind_abbr = serializers.CharField(source='liquor_kind.liquor_kind_abbr', read_only=True)
    liquor_type_desc = serializers.CharField(source='liquor_type.liquor_type_desc', read_only=True)

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
