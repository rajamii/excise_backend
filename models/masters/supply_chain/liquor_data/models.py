from django.db import models

class LiquorData(models.Model):
    sl_no = models.IntegerField(blank=True, null=True, db_column='slno')
    manufacturing_unit_name = models.CharField(max_length=255, blank=True, null=True, db_column='manufacturingunitname')
    brand_owner = models.CharField(max_length=255, blank=True, null=True, db_column='brandowner')
    liquor_type = models.CharField(max_length=100, blank=True, null=True, db_column='liquortype')
    brand_name = models.CharField(max_length=255, blank=True, null=True, db_column='brandname')
    pack_size_ml = models.IntegerField(blank=True, null=True, db_column='packsize_ml')
    purpose_of_sale = models.CharField(max_length=255, blank=True, null=True, db_column='purposeofsale')
    ex_factory_price_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='exfactoryprice_rspercase')
    excise_duty_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='exciseduty_rspercase')
    education_cess_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='educationcess_rspercase')
    additional_excise_duty_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='additionalexciseduty_rspercase')
    additional_excise_duty_12_5_percent_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='additionalexciseduty_12_5percent_rspercase')
    mrp_rs_per_bottle = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='mrp_rsperbottle')
    bottling_fee_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='bottlingfee_rspercase')
    export_fee_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='exportfee_rspercase')
    licensee_id_no = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        db_table = 'liquor_data_details' 
        ordering = ['id']
        verbose_name = 'Liquor Data'
        verbose_name_plural = 'Liquor Data'

    def __str__(self):
        return f"{self.brand_name} - {self.manufacturing_unit_name}"