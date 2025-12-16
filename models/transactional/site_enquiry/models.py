from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import now


def upload_site_image(instance, filename):
    app_label = instance.content_object._meta.app_label
    model_name = instance.content_object._meta.model_name
    app_id = instance.content_object.application_id
    return f"site_enquiry/{app_label}/{model_name}/{app_id}/{filename}"


class SiteEnquiryReport(models.Model):
    # Polymorphic relation: works with LicenseApplication OR NewLicenseApplication
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=50)  # application_id is string PK
    content_object = GenericForeignKey('content_type', 'object_id')

    # === Worship Place ===
    has_traditional_place = models.BooleanField(default=False)
    traditional_place_distance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    traditional_place_name = models.CharField(max_length=1000, blank=True)
    traditional_place_nature = models.CharField(max_length=1000, blank=True)
    traditional_place_construction = models.CharField(
        max_length=20,
        choices=[('rcc', 'RCC'), ('wooden_structure', 'Wooden Structure'), ('temporary', 'Temporary')],
        blank=True, null=True
    )

    # === Educational Institution ===
    has_educational_institution = models.BooleanField(default=False)
    educational_institution_distance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    educational_institution_name = models.CharField(max_length=1000, blank=True)
    educational_institution_nature = models.CharField(max_length=1000, blank=True)

    # === Hospital ===
    has_hospital = models.BooleanField(default=False)
    hospital_distance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hospital_name = models.CharField(max_length=1000, blank=True)

    # === Taxi Stand ===
    has_taxi_stand = models.BooleanField(default=False)
    taxi_stand_name = models.CharField(max_length=1000, blank=True)
    taxi_stand_distance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # === Connectivity & Construction ===
    is_interconnected_with_shops = models.BooleanField(default=False)
    interconnectivity_remarks = models.TextField(blank=True)

    shop_construction_type = models.CharField(
        max_length=20,
        choices=[('rcc', 'RCC'), ('wooden_structure', 'Wooden Structure'), ('temporary', 'Temporary')],
    )
    has_excise_shops_nearby = models.BooleanField(default=False)
    nearby_excise_shop_count = models.IntegerField(default=0)
    nearby_excise_shops_remarks = models.TextField(blank=True)

    is_on_highway = models.BooleanField(default=False)
    highway_name = models.TextField(blank=True)

    shop_image_document = models.FileField(upload_to=upload_site_image)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    is_shop_size_correct = models.BooleanField(default=True)
    shop_size_remarks = models.TextField(blank=True)

    enquiry_officer_comments = models.TextField(blank=True)
    additional_enquiry_officer_comments = models.TextField(blank=True)

    # Document verification
    has_id_proof = models.BooleanField()
    id_proof_comments = models.TextField(blank=True)

    has_age_proof = models.BooleanField()
    age_proof_comments = models.TextField(blank=True)

    has_noc_from_landlord = models.BooleanField()
    noc_comments = models.TextField(blank=True)

    has_ownership_proof = models.BooleanField()
    ownership_proof_comments = models.TextField(blank=True)

    has_trade_license = models.BooleanField()
    trade_license_comments = models.TextField(blank=True)

    proposes_barman_or_salesman = models.BooleanField()
    worker_proposal_comments = models.TextField(blank=True)

    worker_docs_valid = models.BooleanField()
    worker_docs_comments = models.TextField(blank=True)

    license_recommendation = models.BooleanField()
    recommendation_comments = models.TextField(blank=True)

    special_remarks = models.TextField(blank=True)
    reporting_place = models.CharField(max_length=250, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'site_enquiry_report'
        unique_together = ('content_type', 'object_id')
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"Site Enquiry - {self.content_object.application_id}"