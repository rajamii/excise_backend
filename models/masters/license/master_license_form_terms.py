from django.db import models
from django.utils.timezone import now

class MasterLicenseFormTerms(models.Model):
    """
    Master table for form terms configurations with different categories and subcategories.
    """
    
    licensee_cat_code = models.IntegerField(
        verbose_name="Licensee Category Code",
        help_text="Primary category code for the license type"
    )
    
    licensee_scat_code = models.IntegerField(
        verbose_name="Licensee Subcategory Code", 
        help_text="Secondary category code for the license type"
    )
    
    sl_no = models.IntegerField(
        verbose_name="Serial Number",
        help_text="Serial Number for multiple terms"
    )
    
    license_terms = models.TextField(
        verbose_name="License Terms",
        help_text="Terms and conditions for the license form",
        null=True,
        blank=True
    )
    
    user_id = models.CharField(
        max_length=50,
        default='admin',
        verbose_name="User ID",
        help_text="User who created/modified the record"
    )
    
    opr_date = models.DateTimeField(
        default=now,
        verbose_name="Operation Date",
        help_text="Date when record was created/modified"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At"
    )
    
    class Meta:
        db_table = 'master_license_form_terms'
        verbose_name = "Master License Form Terms"
        verbose_name_plural = "Master License Form Terms"
        unique_together = [['licensee_cat_code', 'licensee_scat_code', 'sl_no']]
        ordering = ['licensee_cat_code', 'licensee_scat_code', 'sl_no']
        indexes = [
            models.Index(fields=['licensee_cat_code']),
            models.Index(fields=['licensee_scat_code']),
        ]
    
    def __str__(self):
        return f"Terms (Cat: {self.licensee_cat_code}, SubCat: {self.licensee_scat_code}, Sl_No: {self.sl_no})"
