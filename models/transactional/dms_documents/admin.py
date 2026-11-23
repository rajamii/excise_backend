from django.contrib import admin
from .models import DMSUploadedDocument, DMSDocumentCompany, DMSDocumentLabel, DMSTemporaryUpload


@admin.register(DMSUploadedDocument)
class DMSUploadedDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'application_type',
        'application_id',
        'document_field',
        'dms_registration_no',
        'storage_type',
        'dms_reference',
        'is_signed',
        'created_at',
    )
    list_filter = ('application_type', 'storage_type', 'dms_registration_no', 'is_signed', 'created_at')
    search_fields = ('application_id', 'document_field', 'original_filename', 'dms_reference', 'transaction_signature')
    ordering = ('-created_at',)


@admin.register(DMSDocumentCompany)
class DMSDocumentCompanyAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'application_id',
        'document_field',
        'dms_registration_no',
        'storage_type',
        'dms_reference',
        'is_signed',
        'created_at',
    )
    list_filter = ('storage_type', 'dms_registration_no', 'is_signed', 'created_at')
    search_fields = ('application_id', 'document_field', 'original_filename', 'dms_reference', 'transaction_signature')
    ordering = ('-created_at',)


@admin.register(DMSDocumentLabel)
class DMSDocumentLabelAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'application_id',
        'document_field',
        'dms_registration_no',
        'storage_type',
        'dms_reference',
        'is_signed',
        'created_at',
    )
    list_filter = ('storage_type', 'dms_registration_no', 'is_signed', 'created_at')
    search_fields = ('application_id', 'document_field', 'original_filename', 'dms_reference', 'transaction_signature')
    ordering = ('-created_at',)


@admin.register(DMSTemporaryUpload)
class DMSTemporaryUploadAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'username',
        'application_type',
        'document_field',
        'original_filename',
        'file_size',
        'dms_reference',
        'storage_type',
        'created_at',
        'updated_at',
    )
    list_filter = ('application_type', 'storage_type', 'created_at')
    search_fields = ('username', 'document_field', 'original_filename', 'dms_reference')
    ordering = ('-updated_at',)
