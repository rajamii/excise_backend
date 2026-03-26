from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import (
    LiquorData,
    MasterLiquorType,
    MasterLiquorCategory,
    MasterBottleType,
    MasterBrandList,
    MasterFactoryList,
)

class LiquorDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = LiquorData
        fields = ['id', 'brand_name', 'pack_size_ml','education_cess_rs_per_case',
            'excise_duty_rs_per_case',
            'additional_excise_duty_rs_per_case',]


class MasterLiquorTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterLiquorType
        fields = ['id', 'liquor_type', 'is_sync']
        read_only_fields = ['id', 'is_sync']


class MasterLiquorCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterLiquorCategory
        fields = ['id', 'size_ml', 'is_sync']
        read_only_fields = ['id', 'is_sync']


class MasterBottleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterBottleType
        fields = ['id', 'bottle_type', 'is_active', 'is_sync']
        read_only_fields = ['id', 'is_sync']


class MasterBrandListSerializer(serializers.ModelSerializer):
    factory_id = serializers.PrimaryKeyRelatedField(
        source='factory',
        queryset=MasterFactoryList.objects.all(),
        required=False,
        allow_null=True,
    )
    factory_name = serializers.CharField(source='factory.factory_name', read_only=True)

    liquor_type_id = serializers.PrimaryKeyRelatedField(
        source='liquor_type',
        queryset=MasterLiquorType.objects.all(),
        required=False,
        allow_null=True,
    )
    liquor_type = serializers.CharField(source='liquor_type.liquor_type', read_only=True)

    class Meta:
        model = MasterBrandList
        fields = ['id', 'brand_name', 'factory_id', 'factory_name', 'liquor_type_id', 'liquor_type', 'is_sync']
        read_only_fields = ['id', 'is_sync']

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Keep response minimal for dropdowns: IDs only.
        data.pop('factory_name', None)
        data.pop('liquor_type', None)

        return data


class MasterFactoryListSerializer(serializers.ModelSerializer):
    source_content_type = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
        required=False,
        allow_null=True,
    )
    source_application = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MasterFactoryList
        fields = ['id', 'factory_name', 'source_content_type', 'source_object_id', 'source_application', 'is_sync']
        read_only_fields = ['id', 'is_sync']

    def get_source_application(self, obj):
        if not obj.source_content_type_id or not obj.source_object_id:
            return None
        return {
            'source_content_type': obj.source_content_type_id,
            'source_object_id': obj.source_object_id,
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Keep API clean: don't include generic-relation fields when they are null.
        if data.get('source_content_type') is None:
            data.pop('source_content_type', None)
        if data.get('source_object_id') in (None, ''):
            data.pop('source_object_id', None)
        if data.get('source_application') is None:
            data.pop('source_application', None)

        return data

class BrandSizeSerializer(serializers.Serializer):
    brand_name = serializers.CharField()
    sizes = serializers.ListField(child=serializers.IntegerField())
    
    def to_representation(self, instance):
        return {
            'brand_name': instance['brand_name'],
            'sizes': instance['sizes']
        }
