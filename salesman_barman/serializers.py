from rest_framework import serializers
from django.core.files.base import ContentFile

import base64
import imghdr

from django.conf import settings  # Import settings for MEDIA_ROOT
from .models import SalesmanBarmanModel
from .helpers import (
    MODE_OF_OPERATION_CHOICES,
    DISTRICT_CHOICES,
    LICENSE_CATEGORY_CHOICES,
    GENDER_CHOICES,
    NATIONALITY_CHOICES,
    validate_pan_number,
    validate_aadhar_number,
    validate_phone_number,
    validate_address,
    validate_email,
)

class Base64ImageField(serializers.ImageField):

   def to_internal_value(self, data):
        if isinstance(data, str) and data.startswith('data:image'):
            header, encoded = data.split(';base64,')
            try:
                decoded_file = base64.b64decode(encoded)
            except TypeError:
                self.fail('invalid_image')

            file_name = f'{self.field_name}.{imghdr.what(None, h=decoded_file) or "png"}'
            data = ContentFile(decoded_file, name=file_name)
        return super().to_internal_value(data)

class Base64FileField(serializers.FileField):

   def to_internal_value(self, data):
        if isinstance(data, str) and data.startswith('data:'):
            header, encoded = data.split(';base64,')
            try:
                decoded_file = base64.b64decode(encoded)
            except TypeError:
                self.fail('invalid')

            file_type = header.split(':')[1].split(';')[0].split('/')[1] if '/' in header and ';' in header else 'bin'
            file_name = f'{self.field_name}.{file_type}'
            data = ContentFile(decoded_file, name=file_name)
        return super().to_internal_value(data)

class SalesmanBarmanSerializer(serializers.ModelSerializer):
    passPhoto_base64 = Base64ImageField(write_only=True, required=False, allow_null=True)
    aadharCard_base64 = Base64FileField(write_only=True, required=False, allow_null=True)
    residentialCertificate_base64 = Base64FileField(write_only=True, required=False, allow_null=True)
    dateofBirthProof_base64 = Base64FileField(write_only=True, required=False, allow_null=True)

    passPhoto = serializers.ImageField(read_only=True)
    aadharCard = serializers.FileField(read_only=True)
    residentialCertificate = serializers.FileField(read_only=True)
    dateofBirthProof = serializers.FileField(read_only=True)

    class Meta:
        model = SalesmanBarmanModel
        fields = [
            'id', 'role', 'firstName', 'middleName', 'lastName', 'fatherHusbandName',
            'gender', 'dob', 'nationality', 'address', 'pan_number', 'aadhaar',
            'mobileNumber', 'emailId', 'sikkimSubject', 'applicationYear',
            'applicationId', 'applicationDate', 'district', 'licenseCategory',
            'licenseType', 'passPhoto', 'aadharCard', 'residentialCertificate',
            'dateofBirthProof', 'passPhoto_base64', 'aadharCard_base64',
            'residentialCertificate_base64', 'dateofBirthProof_base64'
        ]
        read_only_fields = ['id', 'passPhoto', 'aadharCard', 'residentialCertificate', 'dateofBirthProof']
        extra_kwargs = {
            'applicationId': {'read_only': True} # Assuming applicationId is generated or set elsewhere
        }

    def validate_emailId(self, value):
        validate_email(value)
        return value

    def validate_pan_number(self, value):
        validate_pan_number(value)
        return value

    def validate_aadhaar(self, value):
        validate_aadhar_number(value)
        return value

    def validate_mobileNumber(self, value):
        validate_phone_number(value)
        return value

    def validate_address(self, value):
        validate_address(value)
        return value

    def create(self, validated_data):
        passPhoto_base64 = validated_data.pop('passPhoto_base64', None)
        aadharCard_base64 = validated_data.pop('aadharCard_base64', None)
        residentialCertificate_base64 = validated_data.pop('residentialCertificate_base64', None)
        dateofBirthProof_base64 = validated_data.pop('dateofBirthProof_base64', None)

        instance = SalesmanBarmanModel.objects.create(**validated_data)

        # setting value to be refereneced by the imagefield and base64 functions 
        
        setattr(instance, '_usr_email', instance.emailId)

        if passPhoto_base64:
            instance.passPhoto.save(passPhoto_base64.name, passPhoto_base64, save=False)
        if aadharCard_base64:
            instance.aadharCard.save(aadharCard_base64.name, aadharCard_base64, save=False)
        if residentialCertificate_base64:
            instance.residentialCertificate.save(residentialCertificate_base64.name, residentialCertificate_base64, save=False)
        if dateofBirthProof_base64:
            instance.dateofBirthProof.save(dateofBirthProof_base64.name, dateofBirthProof_base64, save=False)

        instance.save()
        return instance

    def update(self, instance, validated_data):

        passPhoto_base64 = validated_data.pop('passPhoto_base64', None)
        aadharCard_base64 = validated_data.pop('aadharCard_base64', None)
        residentialCertificate_base64 = validated_data.pop('residentialCertificate_base64', None)
        dateofBirthProof_base64 = validated_data.pop('dateofBirthProof_base64', None)

        instance.role = validated_data.get('role', instance.role)
        instance.firstName = validated_data.get('firstName', instance.firstName)
        instance.middleName = validated_data.get('middleName', instance.middleName)
        instance.lastName = validated_data.get('lastName', instance.lastName)
        instance.fatherHusbandName = validated_data.get('fatherHusbandName', instance.fatherHusbandName)
        instance.gender = validated_data.get('gender', instance.gender)
        instance.dob = validated_data.get('dob', instance.dob)
        instance.nationality = validated_data.get('nationality', instance.nationality)
        instance.address = validated_data.get('address', instance.address)
        instance.pan_number = validated_data.get('pan_number', instance.pan_number)
        instance.aadhaar = validated_data.get('aadhaar', instance.aadhaar)
        instance.mobileNumber = validated_data.get('mobileNumber', instance.mobileNumber)
        instance.emailId = validated_data.get('emailId', instance.emailId)
        instance.sikkimSubject = validated_data.get('sikkimSubject', instance.sikkimSubject)
        instance.applicationYear = validated_data.get('applicationYear', instance.applicationYear)
        instance.applicationDate = validated_data.get('applicationDate', instance.applicationDate)
        instance.district = validated_data.get('district', instance.district)
        instance.licenseCategory = validated_data.get('licenseCategory', instance.licenseCategory)
        instance.licenseType = validated_data.get('licenseType', instance.licenseType)

        setattr(instance, '_usr_email', instance.emailId)

        if passPhoto_base64:
            instance.passPhoto.save(passPhoto_base64.name, passPhoto_base64, save=False)
        if aadharCard_base64:
            instance.aadharCard.save(aadharCard_base64.name, aadharCard_base64, save=False)
        if residentialCertificate_base64:
            instance.residentialCertificate.save(residentialCertificate_base64.name, residentialCertificate_base64, save=False)
        if dateofBirthProof_base64:
            instance.dateofBirthProof.save(dateofBirthProof_base64.name, dateofBirthProof_base64, save=False)

        instance.save()
        return instance
