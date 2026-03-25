from django.db import models


class MasterLiquorType(models.Model):
    liquor_type = models.CharField(max_length=100, unique=True, db_column='liquor_type')
    is_sync = models.IntegerField(default=0, db_column='is_sync')
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        db_table = 'master_liquor_type'
        ordering = ['liquor_type']
        verbose_name = 'Master Liquor Type'
        verbose_name_plural = 'Master Liquor Types'

    def __str__(self):
        return str(self.liquor_type or '').strip()


class MasterLiquorCategory(models.Model):
    """
    Master table for bottle/pack capacities (ml).

    Normalizes `brand_warehouse.capacity_size` so that the warehouse table stores
    this master row `id` while the actual ml value lives here.
    """

    size_ml = models.IntegerField(unique=True, db_column='size_ml')
    is_sync = models.IntegerField(default=0, db_column='is_sync')
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        db_table = 'master_liquor_category'
        ordering = ['size_ml']
        verbose_name = 'Master Liquor Category'
        verbose_name_plural = 'Master Liquor Categories'

    def __str__(self):
        return str(int(self.size_ml or 0))

    def __int__(self):
        return int(self.size_ml or 0)


class MasterBottleType(models.Model):
    """
    Master table for transit permit bottle types.

    This is migrated from the old `transit_permit_bottle_types` table and renamed to
    `master_bottle_type` so liquor-related masters stay in this app.
    """

    bottle_type = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    is_sync = models.IntegerField(default=0, db_column='is_sync')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'master_bottle_type'
        verbose_name = 'Master Bottle Type'
        verbose_name_plural = 'Master Bottle Types'
        ordering = ['bottle_type']

    def __str__(self):
        return str(self.bottle_type or '').strip()


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
