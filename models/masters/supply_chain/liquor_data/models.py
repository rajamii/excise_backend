from django.db import models

class LiquorData(models.Model):
    sl_no = models.IntegerField(blank=True, null=True, db_column='sl_no')
    manufacturing_unit_name = models.CharField(max_length=255, blank=True, null=True, db_column='manufacturing_unit_name')
    brand_owner = models.CharField(max_length=255, blank=True, null=True, db_column='brand_owner')
    liquor_type = models.CharField(max_length=100, blank=True, null=True, db_column='liquor_type')
    brand_name = models.CharField(max_length=255, blank=True, null=True, db_column='brand_name')
    pack_size_ml = models.IntegerField(blank=True, null=True, db_column='pack_size_ml')
    purpose_of_sale = models.CharField(max_length=255, blank=True, null=True, db_column='purpose_of_sale')
    ex_factory_price_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='ex_factory_price_rs_per_case')
    excise_duty_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='excise_duty_rs_per_case')
    education_cess_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='education_cess_rs_per_case')
    additional_excise_duty_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='additional_excise_duty_rs_per_case')
    additional_excise_duty_12_5_percent_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='additional_excise_duty_12_5_percent_rs_per_case')
    mrp_rs_per_bottle = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='mrp_rs_per_bottle')
    bottling_fee_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='bottling_fee_rs_per_case')
    export_fee_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='export_fee_rs_per_case')
    status = models.CharField(max_length=50, blank=True, null=True, db_column='status')
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        db_table = 'liquor_data_details' 
        ordering = ['id']
        verbose_name = 'Liquor Data'
        verbose_name_plural = 'Liquor Data'

    def __str__(self):
        return f"{self.brand_name} - {self.manufacturing_unit_name}"