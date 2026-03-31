from django.db import models
from django.utils.timezone import now


def current_time():
    return now().time()


class MasterLicenseForm(models.Model):
    """
    Master table for license form configurations with different categories and subcategories.
    This stores the template information for different types of licenses including
    counter foil statements and terms declarations.
    """
    
    licensee_cat_code = models.IntegerField(
        verbose_name="Licensee Category Code",
        help_text="Primary category code for the license type"
    )
    
    licensee_scat_code = models.IntegerField(
        verbose_name="Licensee Subcategory Code", 
        help_text="Secondary category code for the license type"
    )
    
    license_title = models.CharField(
        max_length=500,
        verbose_name="License Title",
        help_text="Title of the license type"
    )
    
    counter_foil_statement_1 = models.TextField(
        blank=True,
        null=True,
        verbose_name="Counter Foil Statement 1",
        help_text="First counter foil statement for the license"
    )
    
    counter_foil_statement_2 = models.TextField(
        blank=True,
        null=True,
        verbose_name="Counter Foil Statement 2",
        help_text="Second counter foil statement for the license"
    )
    
    counter_foil_statement_3 = models.TextField(
        blank=True,
        null=True,
        verbose_name="Counter Foil Statement 3",
        help_text="Third counter foil statement for the license"
    )
    
    terms_declaration_statement = models.TextField(
        blank=True,
        null=True,
        verbose_name="Terms Declaration Statement",
        help_text="Terms and conditions declaration statement"
    )
    
    opr_date = models.TimeField(
        default=current_time,
        verbose_name="Operation Time",
        help_text="Time when record was created/modified"
    )
    
    user_id = models.CharField(
        max_length=50,
        default='admin',
        verbose_name="User ID",
        help_text="User who created/modified the record"
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
        db_table = 'master_license_form'
        verbose_name = "Master License Form"
        verbose_name_plural = "Master License Forms"
        unique_together = [['licensee_cat_code', 'licensee_scat_code']]
        ordering = ['licensee_cat_code', 'licensee_scat_code']
        indexes = [
            models.Index(fields=['licensee_cat_code']),
            models.Index(fields=['licensee_scat_code']),
            models.Index(fields=['license_title']),
        ]
    
    def __str__(self):
        return f"{self.license_title} (Cat: {self.licensee_cat_code}, SubCat: {self.licensee_scat_code})"
    
    @classmethod
    def get_license_config(cls, cat_code: int, scat_code: int):
        """
        Get license configuration by category and subcategory codes.
        
        Args:
            cat_code: Licensee category code
            scat_code: Licensee subcategory code
            
        Returns:
            MasterLicenseForm instance or None if not found
        """
        try:
            return cls.objects.get(
                licensee_cat_code=cat_code,
                licensee_scat_code=scat_code
            )
        except cls.DoesNotExist:
            return None
