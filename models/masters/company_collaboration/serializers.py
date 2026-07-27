from rest_framework import serializers

from .models import BrandOwner, BrandOwnerFee, BrandOwnerType, LiquorBrand, LiquorKind, LiquorType, LiquorCategory, master_Brand_owner


def _category_label(code):
    if code is None:
        return ""
    try:
        return LiquorCategory.objects.get(pk=code).liquor_cat_desc
    except LiquorCategory.DoesNotExist:
        return f"Category {code}"


def _type_label(code):
    return f"Type {code}" if code is not None else ""


class BrandOwnerTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandOwnerType
        fields = ['brand_owner_type_code', 'brand_owner_type_desc']
        # Allow code to be set on create but not on update
        extra_kwargs = {
            'brand_owner_type_code': {'required': True}
        }


class CompanyDetailSerializer(serializers.ModelSerializer):
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


class BrandOwnerSerializer(serializers.ModelSerializer):
    brand_owner_code = serializers.CharField(source='Liquor_BOwner_Code', required=True)
    brand_owner_type = serializers.IntegerField(source='Brand_Owner_Type_Code', required=False, allow_null=True)
    brand_owner_type_desc = serializers.SerializerMethodField()
    brand_owner_name = serializers.CharField(source='Liquor_BOwner_Name', required=False, allow_blank=True, allow_null=True)
    brand_owner_mobile_no = serializers.SerializerMethodField()
    brand_owner_company_address = serializers.CharField(source='Liquor_BOwner_Address', required=False, allow_blank=True, allow_null=True)
    brand_owner_address = serializers.CharField(source='Liquor_BOwner_Address', required=False, allow_blank=True, allow_null=True)
    brand_owner_pincode = serializers.CharField(source='Liquor_BOwner_PinCode', required=False, allow_blank=True, allow_null=True)
    brand_owner_pan = serializers.SerializerMethodField()
    brand_owner_email = serializers.SerializerMethodField()
    brand_owner_origin = serializers.CharField(source='Liquor_BOwner_Origin', required=False, allow_blank=True, allow_null=True)
    brand_owner_country = serializers.SerializerMethodField()
    brand_owner_state = serializers.SerializerMethodField()
    liquor_bowner_code = serializers.CharField(source='Liquor_BOwner_Code', required=False, allow_blank=True, allow_null=True)
    brand_owner_licensee_id_no = serializers.CharField(source='Licensee_id_no', required=False, allow_blank=True, allow_null=True)
    parent_licensee_id_no = serializers.CharField(source='Licensee_id_no', required=False, allow_blank=True, allow_null=True)
    renewed_upto = serializers.SerializerMethodField()
    enable_status = serializers.SerializerMethodField()
    user_id = serializers.SerializerMethodField()

    class Meta:
        model = master_Brand_owner
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
            'user_id',
        ]

    def get_brand_owner_type_desc(self, obj):
        code = obj.Brand_Owner_Type_Code
        if code == 1:
            return "Manufactured in Sikkim"
        elif code == 2:
            return "Imported from other States/Country"
        elif code == 3:
            return "Bottled in Sikkim (Collaboration)"
        return f"Type {code}" if code else ""

    def get_brand_owner_mobile_no(self, obj):
        return ""

    def get_brand_owner_pan(self, obj):
        try:
            from .models import BrandOwner
            old = BrandOwner.objects.filter(brand_owner_name__iexact=obj.Liquor_BOwner_Name).first()
            if old and old.brand_owner_pan:
                return old.brand_owner_pan
        except Exception:
            pass
        return "DPZAB1234P"

    def get_brand_owner_email(self, obj):
        return ""

    def get_brand_owner_country(self, obj):
        return 87

    def get_brand_owner_state(self, obj):
        try:
            return int(obj.Liquor_BOwner_State)
        except Exception:
            return 28

    def get_renewed_upto(self, obj):
        return None

    def get_enable_status(self, obj):
        return 'D' if obj.Delete_Status == 'Y' else 'E'

    def get_user_id(self, obj):
        return ""

    def create(self, validated_data):
        code = validated_data.get('Liquor_BOwner_Code')
        if not code:
            raise serializers.ValidationError({"brand_owner_code": "This field is required."})
        
        obj_data = {
            'Liquor_BOwner_Code': code,
            'Liquor_BOwner_Origin': validated_data.get('Liquor_BOwner_Origin', 'I'),
            'Liquor_BOwner_Country': 'India',
            'Liquor_BOwner_State': validated_data.get('Liquor_BOwner_State', '28'),
            'Liquor_BOwner_Name': validated_data.get('Liquor_BOwner_Name', ''),
            'Liquor_BOwner_Address': validated_data.get('Liquor_BOwner_Address', ''),
            'Liquor_BOwner_PinCode': validated_data.get('Liquor_BOwner_PinCode', ''),
            'Licensee_id_no': validated_data.get('Licensee_id_no', ''),
            'Brand_Owner_Type_Code': validated_data.get('Brand_Owner_Type_Code', 1),
            'Delete_Status': 'N',
        }
        return master_Brand_owner.objects.create(**obj_data)

    def update(self, instance, validated_data):
        instance.Liquor_BOwner_Origin = validated_data.get('Liquor_BOwner_Origin', instance.Liquor_BOwner_Origin)
        instance.Liquor_BOwner_State = validated_data.get('Liquor_BOwner_State', instance.Liquor_BOwner_State)
        instance.Liquor_BOwner_Name = validated_data.get('Liquor_BOwner_Name', instance.Liquor_BOwner_Name)
        
        address = validated_data.get('Liquor_BOwner_Address')
        if address:
            instance.Liquor_BOwner_Address = address
            
        instance.Liquor_BOwner_PinCode = validated_data.get('Liquor_BOwner_PinCode', instance.Liquor_BOwner_PinCode)
        instance.Licensee_id_no = validated_data.get('Licensee_id_no', instance.Licensee_id_no)
        instance.Brand_Owner_Type_Code = validated_data.get('Brand_Owner_Type_Code', instance.Brand_Owner_Type_Code)
        instance.save()
        return instance


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


class LiquorCategoryCRUDSerializer(serializers.ModelSerializer):
    class Meta:
        model = LiquorCategory
        fields = ['liquor_cat_code', 'liquor_cat_desc', 'liquor_cat_abbr', 'delete_status']


class LiquorKindCRUDSerializer(serializers.ModelSerializer):
    liquor_cat_desc = serializers.SerializerMethodField()

    def get_liquor_cat_desc(self, obj):
        try:
            return LiquorCategory.objects.get(pk=obj.liquor_cat).liquor_cat_desc
        except LiquorCategory.DoesNotExist:
            return ''

    class Meta:
        model = LiquorKind
        fields = ['id', 'liquor_cat', 'liquor_cat_desc', 'liquor_kind_code', 'liquor_kind_desc', 'liquor_kind_abbr', 'delete_status']


class LiquorTypeCRUDSerializer(serializers.ModelSerializer):
    liquor_cat_desc = serializers.SerializerMethodField()
    liquor_kind_desc = serializers.CharField(source='liquor_kind.liquor_kind_desc', read_only=True)

    def get_liquor_cat_desc(self, obj):
        try:
            return LiquorCategory.objects.get(pk=obj.liquor_cat).liquor_cat_desc
        except LiquorCategory.DoesNotExist:
            return ''

    class Meta:
        model = LiquorType
        fields = ['id', 'liquor_cat', 'liquor_cat_desc', 'liquor_kind', 'liquor_kind_desc', 'liquor_type_code', 'liquor_type_desc', 'liquor_type_code_old', 'delete_status']


class LiquorBrandCRUDSerializer(serializers.ModelSerializer):
    liquor_cat_desc = serializers.SerializerMethodField()
    liquor_kind_desc = serializers.CharField(source='liquor_kind.liquor_kind_desc', read_only=True)
    liquor_type_desc = serializers.SerializerMethodField()

    def get_liquor_cat_desc(self, obj):
        try:
            return LiquorCategory.objects.get(pk=obj.liquor_cat).liquor_cat_desc
        except LiquorCategory.DoesNotExist:
            return ''

    def get_liquor_type_desc(self, obj):
        # Use filter().first() instead of .get() to avoid MultipleObjectsReturned
        lt = LiquorType.objects.filter(
            liquor_cat=obj.liquor_cat,
            liquor_kind_id=obj.liquor_kind_id,
            liquor_type_code=obj.liquor_type,
            delete_status='N'
        ).first()
        if lt:
            return lt.liquor_type_desc
        # Fallback: match only by type_code in case cat/kind don't align
        lt = LiquorType.objects.filter(
            liquor_type_code=obj.liquor_type,
            delete_status='N'
        ).first()
        return lt.liquor_type_desc if lt else ''

    class Meta:
        model = LiquorBrand
        fields = [
            'id',
            'liquor_brand_code',
            'liquor_cat',
            'liquor_cat_desc',
            'liquor_kind',
            'liquor_kind_desc',
            'liquor_type',
            'liquor_type_desc',
            'liquor_brand_desc',
            'brand_name_alias',
            'liquor_type_code_old',
            'entry_flag',
            'delete_status'
        ]


class LiquorBrandSerializer(serializers.ModelSerializer):
    liquor_cat_desc  = serializers.SerializerMethodField()
    liquor_kind_desc = serializers.CharField(source='liquor_kind.liquor_kind_desc', read_only=True)
    liquor_kind_abbr = serializers.CharField(source='liquor_kind.liquor_kind_abbr', read_only=True)
    liquor_type_desc = serializers.SerializerMethodField()

    def get_liquor_cat_desc(self, obj):
        return _category_label(getattr(obj, 'liquor_cat', None))

    def get_liquor_type_desc(self, obj):
        try:
            lt = LiquorType.objects.get(
                liquor_cat=obj.liquor_cat,
                liquor_kind_id=obj.liquor_kind_id,
                liquor_type_code=obj.liquor_type
            )
            return lt.liquor_type_desc
        except LiquorType.DoesNotExist:
            return _type_label(getattr(obj, 'liquor_type', None))

    class Meta:
        model = LiquorBrand
        fields = [
            'id',
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
            'pack_sizes',
        ]

    pack_sizes = serializers.SerializerMethodField()

    def get_pack_sizes(self, obj):
        from .models import LiquorProduct
        sizes = []
        seen_values = set()

        # 1) First check master_liquor_product for real registered sizes for this brand
        if obj.liquor_brand_code:
            products = (
                LiquorProduct.objects
                .filter(liquor_brand_code=obj.liquor_brand_code, delete_status='N')
                .exclude(measure_value__isnull=True)
                .order_by('measure_value')
            )
            for p in products:
                if p.measure_value and p.measure_value not in seen_values:
                    seen_values.add(p.measure_value)
                    unit = p.measure_unit or 'M'
                    display_unit = 'Ml' if unit.strip().upper() in ('M', 'ML') else unit
                    sizes.append({
                        'product_id': p.id,
                        'value': p.measure_value,
                        'unit': display_unit,
                        'label': f"{p.measure_value} {display_unit}",
                    })

        # 2) Fall back to category-based defaults ONLY if no sizes exist in master_liquor_product
        if not sizes:
            if obj.liquor_cat == 3:  # Beer
                defaults = [
                    {'value': 650, 'label': '650 Ml'},
                    {'value': 500, 'label': '500 Ml'},
                    {'value': 330, 'label': '330 Ml'}
                ]
            else:  # Spirits, Wine, Country Liquor, Homemade
                defaults = [
                    {'value': 750, 'label': '750 Ml'},
                    {'value': 375, 'label': '375 Ml'},
                    {'value': 180, 'label': '180 Ml'}
                ]
            for idx, d in enumerate(defaults):
                sizes.append({
                    'product_id': -(obj.id * 10 + idx),
                    'value': d['value'],
                    'unit': 'Ml',
                    'label': d['label']
                })

        sizes.sort(key=lambda x: x['value'], reverse=True)
        return sizes


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
