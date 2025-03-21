from rest_framework import serializers
from .models import SalesmanBarmanDetails, DocumentsDetails

class DocumentsDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentsDetails
        fields = [
            'id', 'passport_size_photo', 'aadhar_card', 'sikkim_subject_certificate', 'date_of_birth_proof'
        ]

class SalesmanBarmanDetailsSerializer(serializers.ModelSerializer):
    # Nested serializer for documents
    documents = DocumentsDetailsSerializer()

    class Meta:
        model = SalesmanBarmanDetails
        fields = [
            'id', 'first_name', 'middle_name', 'last_name', 'father_or_husband_name', 'gender', 'nationality',
            'address', 'pan_number', 'aadhar_number', 'email', 'mode_of_operation', 'application_year', 
            'application_id', 'application_date', 'district', 'license_category', 'license_type', 
            'salesman_specific_field', 'barman_specific_field', 'documents'
        ]
    
    def create(self, validated_data):
        # Extracting the documents data from the validated data
        documents_data = validated_data.pop('documents')
        # Creating DocumentsDetails instance first
        document_instance = DocumentsDetails.objects.create(**documents_data)
        # Creating SalesmanBarmanDetails instance
        salesman_barman_instance = SalesmanBarmanDetails.objects.create(**validated_data)
        # Assigning the created document instance to the SalesmanBarmanDetails instance
        salesman_barman_instance.documents = document_instance
        salesman_barman_instance.save()
        return salesman_barman_instance

    def update(self, instance, validated_data):
        # Extracting the documents data from the validated data
        documents_data = validated_data.pop('documents', None)
        
        # Updating the fields of SalesmanBarmanDetails
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if documents_data:
            # If documents data is provided, update the DocumentsDetails model as well
            for attr, value in documents_data.items():
                setattr(instance.documents, attr, value)
            instance.documents.save()
        
        instance.save()
        return instance
