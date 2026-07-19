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


class BrandOwnerSerializer(serializers.ModelSerializer):
    brand_owner_code = serializers.CharField(source='Liquor_BOwner_Code')
    brand_owner_type = serializers.IntegerField(source='Brand_Owner_Type_Code', allow_null=True)
    brand_owner_type_desc = serializers.SerializerMethodField()
    brand_owner_name = serializers.CharField(source='Liquor_BOwner_Name', allow_blank=True, allow_null=True)
    brand_owner_mobile_no = serializers.SerializerMethodField()
    brand_owner_company_address = serializers.CharField(source='Liquor_BOwner_Address', allow_blank=True, allow_null=True)
    brand_owner_address = serializers.CharField(source='Liquor_BOwner_Address', allow_blank=True, allow_null=True)
    brand_owner_pincode = serializers.CharField(source='Liquor_BOwner_PinCode', allow_blank=True, allow_null=True)
    brand_owner_pan = serializers.SerializerMethodField()
    brand_owner_email = serializers.SerializerMethodField()
    brand_owner_origin = serializers.CharField(source='Liquor_BOwner_Origin', allow_blank=True, allow_null=True)
    brand_owner_country = serializers.SerializerMethodField()
    brand_owner_state = serializers.SerializerMethodField()
    liquor_bowner_code = serializers.CharField(source='Liquor_BOwner_Code', allow_blank=True, allow_null=True)
    brand_owner_licensee_id_no = serializers.CharField(source='Licensee_id_no', allow_blank=True, allow_null=True)
    parent_licensee_id_no = serializers.CharField(source='Licensee_id_no', allow_blank=True, allow_null=True)
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
        seen_labels = set()
        
        # 1) Always populate category-based default standard sizes
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
            label = d['label']
            seen_labels.add(label)
            sizes.append({
                'product_id': -(obj.id * 10 + idx),
                'value': d['value'],
                'unit': 'Ml',
                'label': label
            })
            
        # 2) Merge additional custom sizes from master_liquor_product if available
        if obj.liquor_brand_code:
            products = LiquorProduct.objects.filter(liquor_brand_code=obj.liquor_brand_code)
            for p in products:
                if p.measure_value:
                    unit = p.measure_unit or 'M'
                    display_unit = 'Ml' if unit.strip().upper() in ('M', 'ML') else unit
                    label = f"{p.measure_value} {display_unit}"
                    if label not in seen_labels:
                        seen_labels.add(label)
                        sizes.append({
                            'product_id': p.id,
                            'value': p.measure_value,
                            'unit': display_unit,
                            'label': label,
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
