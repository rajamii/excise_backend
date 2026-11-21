from django.db import models


class DMSUploadedDocument(models.Model):
    """
    Tracks documents uploaded to MongoDB GridFS and Government DMS
    for New License Applications and Salesman / Barman Applications.
    """
    application_type = models.CharField(max_length=50, db_index=True)  # 'new_license', 'salesman_barman'
    application_id = models.CharField(max_length=100, db_index=True)    # e.g. 'NLI/1101/2026-27/0015', 'SBM/101/2026-27/0001'
    document_field = models.CharField(max_length=50, db_index=True)    # e.g. 'pass_photo', 'aadhaar_card', 'passPhoto', etc.
    dms_reference = models.CharField(max_length=255, blank=True, null=True)  # MongoDB GridFS ObjectId or fallback path
    dms_arn = models.CharField(max_length=255, blank=True, null=True)        # ARN sent to Government DMS
    dms_registration_no = models.CharField(max_length=50, default='DMS20260006', blank=True, null=True)
    transaction_signature = models.TextField(blank=True, null=True)         # HMAC-SHA256 signature
    original_filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    storage_type = models.CharField(max_length=50, default='DMS_MONGODB')   # 'DMS_MONGODB' or 'LOCAL_FALLBACK'
    is_signed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dms_uploaded_document_new'
        indexes = [
            models.Index(fields=['application_type', 'application_id']),
            models.Index(fields=['application_id', 'document_field']),
            models.Index(fields=['dms_registration_no']),
        ]
        unique_together = [('application_id', 'document_field')]
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.application_type}] {self.application_id} - {self.document_field} ({self.storage_type})"


# Alias for explicit naming
DMSUploadedDocumentNew = DMSUploadedDocument


class DMSDocumentCompany(models.Model):
    """
    Dedicated table for tracking documents uploaded to MongoDB GridFS and Government DMS
    specifically for Company Registration Applications.
    """
    application_type = models.CharField(max_length=50, default='company_registration', db_index=True)
    application_id = models.CharField(max_length=100, db_index=True)    # e.g. 'COMP/2026-27/0001'
    document_field = models.CharField(max_length=50, db_index=True)    # e.g. 'excise_license', 'deed_of_partnership'
    dms_reference = models.CharField(max_length=255, blank=True, null=True)  # MongoDB GridFS ObjectId or fallback path
    dms_arn = models.CharField(max_length=255, blank=True, null=True)
    dms_registration_no = models.CharField(max_length=50, default='DMS20260006', blank=True, null=True)
    transaction_signature = models.TextField(blank=True, null=True)         # HMAC-SHA256 signature
    original_filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    storage_type = models.CharField(max_length=50, default='DMS_MONGODB')   # 'DMS_MONGODB' or 'LOCAL_FALLBACK'
    is_signed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dms_document_company'
        indexes = [
            models.Index(fields=['application_type', 'application_id']),
            models.Index(fields=['application_id', 'document_field']),
            models.Index(fields=['dms_registration_no']),
        ]
        unique_together = [('application_id', 'document_field')]
        ordering = ['-created_at']

    def __str__(self):
        return f"[company_registration] {self.application_id} - {self.document_field} ({self.storage_type})"
