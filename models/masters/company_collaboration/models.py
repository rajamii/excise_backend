from django.db import models


# ---------------------------------------------------------------------------
# MM_Brand_Owner_Master_Type  →  master_brand_owner_type
# ---------------------------------------------------------------------------

class BrandOwnerType(models.Model):
    """
    Lookup table for brand owner classification.
    Type 1 = Manufactured in Sikkim
    Type 2 = Imported from other States/Country
    Type 3 = Bottled in Sikkim (Collaboration)
    """
    brand_owner_type_code = models.PositiveSmallIntegerField(primary_key=True)
    brand_owner_type_desc = models.CharField(max_length=100)

    class Meta:
        db_table = 'master_brand_owner_type'
        managed = False
        ordering = ['brand_owner_type_code']

    def __str__(self):
        return f"{self.brand_owner_type_code} — {self.brand_owner_type_desc}"


# ---------------------------------------------------------------------------
# MM_Brand_Owner_Master  →  master_brand_owner
# ---------------------------------------------------------------------------

class BrandOwner(models.Model):
    """
    Master list of brand owners (distilleries / importers / collaborators).
    brand_owner_code is the natural PK (e.g. B01/2023/025).
    """
    ENABLE_STATUS_CHOICES = [('E', 'Enabled'), ('D', 'Disabled')]
    ORIGIN_CHOICES = [('I', 'India'), ('F', 'Foreign')]

    brand_owner_code = models.CharField(max_length=30, primary_key=True)
    brand_owner_type = models.ForeignKey(
        BrandOwnerType,
        on_delete=models.PROTECT,
        related_name='brand_owners',
        db_column='brand_owner_type_code',
    )
    brand_owner_name = models.CharField(max_length=255)
    brand_owner_mobile_no = models.CharField(max_length=15, blank=True, null=True)
    brand_owner_company_address = models.TextField(blank=True, null=True)
    brand_owner_address = models.TextField(blank=True, null=True)
    brand_owner_pincode = models.CharField(max_length=10, blank=True, null=True)
    brand_owner_pan = models.CharField(max_length=20, blank=True, null=True)
    brand_owner_email = models.EmailField(blank=True, null=True)

    # Geographic references (stored as raw codes to avoid tight coupling)
    brand_owner_origin = models.CharField(max_length=1, choices=ORIGIN_CHOICES, default='I')
    brand_owner_country = models.IntegerField(blank=True, null=True)
    brand_owner_state = models.IntegerField(blank=True, null=True)

    # Licensee linkage
    liquor_bowner_code = models.CharField(max_length=30, blank=True, null=True)
    brand_owner_licensee_id_no = models.CharField(max_length=30, blank=True, null=True)
    parent_licensee_id_no = models.CharField(max_length=30, blank=True, null=True)
    renewed_upto = models.DateField(blank=True, null=True)

    enable_status = models.CharField(max_length=1, choices=ENABLE_STATUS_CHOICES, default='E')
    opr_date = models.DateTimeField(auto_now_add=True)
    user_id = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        db_table = 'master_brand_owner'
        managed = False
        ordering = ['brand_owner_code']
        indexes = [
            models.Index(fields=['brand_owner_name'], name='mbo_name_idx'),
            models.Index(fields=['brand_owner_type'], name='mbo_type_idx'),
            models.Index(fields=['enable_status'],    name='mbo_status_idx'),
        ]

    def __str__(self):
        return f"{self.brand_owner_code} — {self.brand_owner_name}"


# ---------------------------------------------------------------------------
# MM_Liquor_Kind  →  master_liquor_kind
# ---------------------------------------------------------------------------

class LiquorKind(models.Model):
    """
    Sub-classification within a category: IMFL, OSBI, Beer, etc.
    Composite PK: (liquor_cat_code, liquor_kind_code).
    """
    liquor_cat = models.PositiveSmallIntegerField(db_column='liquor_cat_code')
    liquor_kind_code = models.PositiveSmallIntegerField()
    liquor_kind_desc = models.CharField(max_length=100)
    liquor_kind_abbr = models.CharField(max_length=20)
    delete_status = models.CharField(max_length=1, default='N')

    class Meta:
        db_table = 'master_liquor_kind'
        managed = False
        unique_together = [('liquor_cat', 'liquor_kind_code')]
        ordering = ['liquor_cat', 'liquor_kind_code']

    def __str__(self):
        return f"{self.liquor_kind_abbr} — {self.liquor_kind_desc}"


# ---------------------------------------------------------------------------
# MM_Liquor_Brand  →  master_liquor_brand
# ---------------------------------------------------------------------------

class LiquorBrand(models.Model):
    """
    Individual brand registered under a liquor type.
    """
    id = models.BigAutoField(primary_key=True)
    liquor_brand_code = models.CharField(max_length=20)
    liquor_cat = models.PositiveSmallIntegerField(db_column='liquor_cat_code')
    liquor_kind = models.ForeignKey(
        LiquorKind,
        on_delete=models.PROTECT,
        related_name='brands',
        db_column='liquor_kind_id',
    )
    liquor_type = models.PositiveBigIntegerField(db_column='liquor_type_id')
    liquor_brand_desc = models.CharField(max_length=255)
    brand_name_alias = models.CharField(max_length=20, blank=True, null=True)
    liquor_type_code_old = models.CharField(max_length=20, blank=True, null=True)
    entry_flag = models.CharField(max_length=10, blank=True, null=True)
    delete_status = models.CharField(max_length=1, default='N')

    class Meta:
        db_table = 'master_liquor_brand'
        managed = False
        ordering = ['liquor_brand_code']
        indexes = [
            models.Index(fields=['liquor_brand_desc'], name='mlb_desc_idx'),
            models.Index(fields=['liquor_cat'],        name='mlb_cat_idx'),
            models.Index(fields=['liquor_type'],       name='mlb_type_idx'),
            models.Index(fields=['delete_status'],     name='mlb_del_idx'),
        ]

    def __str__(self):
        return f"{self.liquor_brand_code} — {self.liquor_brand_desc}"


# ---------------------------------------------------------------------------
# MM_Brand_Owner_Master_Fees  →  master_brand_owner_fee
# ---------------------------------------------------------------------------

class BrandOwnerFee(models.Model):
    """
    Fee structure for company collaboration applications.
    Only one active record is expected at a time.
    """
    ACTIVE_STATUS_CHOICES = [('A', 'Active'), ('I', 'Inactive')]

    registration_fee = models.DecimalField(max_digits=12, decimal_places=2)
    collaboration_fees = models.DecimalField(max_digits=12, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=12, decimal_places=2)
    active_status = models.CharField(max_length=1, choices=ACTIVE_STATUS_CHOICES, default='A')
    from_date = models.DateTimeField()
    to_date = models.DateTimeField(blank=True, null=True)
    user_id = models.CharField(max_length=50, blank=True, null=True)
    opr_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'master_brand_owner_fee'
        managed = False
        ordering = ['-from_date']

    def __str__(self):
        return f"Fee: reg={self.registration_fee} collab={self.collaboration_fees} deposit={self.security_deposit}"


# ---------------------------------------------------------------------------
# MM_Liquor_Product  →  master_liquor_product
# ---------------------------------------------------------------------------

class LiquorProduct(models.Model):
    """
    Lookup table for liquor product details.
    """
    id = models.BigAutoField(primary_key=True)
    liquor_cat_code = models.SmallIntegerField(blank=True, null=True)
    liquor_kind_code = models.SmallIntegerField(blank=True, null=True)
    liquor_type_code = models.SmallIntegerField(blank=True, null=True)
    liquor_brand_code = models.CharField(max_length=255, blank=True, null=True)
    liquor_reg_type = models.CharField(max_length=255, blank=True, null=True)
    liquor_bottler_origin = models.CharField(max_length=255, blank=True, null=True)
    liquor_bottler_state = models.SmallIntegerField(blank=True, null=True)
    liquor_bottler_code = models.CharField(max_length=255, blank=True, null=True)
    liquor_bowner_origin = models.CharField(max_length=255, blank=True, null=True)
    liquor_bowner_state = models.SmallIntegerField(blank=True, null=True)
    liquor_bowner_code = models.CharField(max_length=255, blank=True, null=True)
    strength_code = models.SmallIntegerField(blank=True, null=True)
    strength_value = models.DecimalField(max_digits=15, decimal_places=4, blank=True, null=True)
    strength_unit = models.CharField(max_length=255, blank=True, null=True)
    measure_code = models.SmallIntegerField(blank=True, null=True)
    measure_value = models.SmallIntegerField(blank=True, null=True)
    measure_unit = models.CharField(max_length=255, blank=True, null=True)
    liquor_retail_price = models.SmallIntegerField(blank=True, null=True)
    liquor_plegend_code = models.SmallIntegerField(blank=True, null=True)
    liquor_slegend_code = models.SmallIntegerField(blank=True, null=True)
    liquor_product_reg_dt = models.CharField(max_length=255, blank=True, null=True)
    liquor_product_reg_val_upto = models.CharField(max_length=255, blank=True, null=True)
    liquor_reg_applicant = models.CharField(max_length=255, blank=True, null=True)
    licensee_id_no = models.CharField(max_length=255, blank=True, null=True)
    liquor_reg_applicant_name = models.CharField(max_length=255, blank=True, null=True)
    label_specification = models.CharField(max_length=255, blank=True, null=True)
    liquor_product_reg_no = models.CharField(max_length=255, blank=True, null=True)
    sl_no = models.CharField(max_length=255, blank=True, null=True)
    renopt_code = models.CharField(max_length=255, blank=True, null=True)
    liquor_type_code_old = models.CharField(max_length=255, blank=True, null=True)
    product_restrict = models.CharField(max_length=255, blank=True, null=True)
    reg_fee_amt = models.SmallIntegerField(blank=True, null=True)
    reg_fee_remarks = models.CharField(max_length=255, blank=True, null=True)
    package_type_code = models.SmallIntegerField(blank=True, null=True)
    prov_prin_bat_no = models.CharField(max_length=255, blank=True, null=True)
    prov_prin_mondate_manuf = models.CharField(max_length=255, blank=True, null=True)
    prov_prin_expiry_date = models.CharField(max_length=255, blank=True, null=True)
    prov_gtin = models.CharField(max_length=255, blank=True, null=True)
    gti_no = models.CharField(max_length=255, blank=True, null=True)
    reason_cancel = models.CharField(max_length=255, blank=True, null=True)
    liquor_product_status = models.SmallIntegerField(blank=True, null=True)
    lic_send_date = models.CharField(max_length=255, blank=True, null=True)
    dcfl_send_date = models.CharField(max_length=255, blank=True, null=True)
    ec_apprv_date = models.CharField(max_length=255, blank=True, null=True)
    delete_status = models.CharField(max_length=255, blank=True, null=True)
    opr_date = models.CharField(max_length=255, blank=True, null=True)
    user_id = models.CharField(max_length=255, blank=True, null=True)
    entry_flag = models.CharField(max_length=255, blank=True, null=True)
    purpose_of_rereg = models.CharField(max_length=255, blank=True, null=True)
    no_of_bottle_per_case = models.SmallIntegerField(blank=True, null=True)
    fssai_status = models.CharField(max_length=255, blank=True, null=True)
    fssai_lic_send_date = models.CharField(max_length=255, blank=True, null=True)
    fssai_dcfl_send_date = models.CharField(max_length=255, blank=True, null=True)
    fssai_ec_apprv_date = models.CharField(max_length=255, blank=True, null=True)
    fssai_cancel_reason = models.CharField(max_length=255, blank=True, null=True)
    allow_grn_upto = models.CharField(max_length=255, blank=True, null=True)
    ssefl_remarks = models.CharField(max_length=255, blank=True, null=True)
    exdist_price_per_case = models.DecimalField(max_digits=15, decimal_places=4, blank=True, null=True)
    excise_duty_per_case = models.DecimalField(max_digits=15, decimal_places=4, blank=True, null=True)
    sale_tax_per_case = models.CharField(max_length=255, blank=True, null=True)
    other_gov_lev = models.CharField(max_length=255, blank=True, null=True)
    land_price_dist_per_case = models.CharField(max_length=255, blank=True, null=True)
    dist_merg_per_case = models.CharField(max_length=255, blank=True, null=True)
    dist_bill_pri_per_case = models.CharField(max_length=255, blank=True, null=True)
    retailer_mergin_per_case = models.CharField(max_length=255, blank=True, null=True)
    mrp_per_case = models.IntegerField(blank=True, null=True)
    measure_desc = models.CharField(max_length=255, blank=True, null=True)
    bevco_allow_flag = models.CharField(max_length=255, blank=True, null=True)
    registration_year = models.CharField(max_length=255, blank=True, null=True)
    export_facility_flag = models.CharField(max_length=255, blank=True, null=True)
    proposed_mrp_per_bottle = models.SmallIntegerField(blank=True, null=True)
    proposed_mrp_per_case = models.IntegerField(blank=True, null=True)
    permit_generate_date = models.CharField(max_length=255, blank=True, null=True)
    strength_value_v_b_v = models.CharField(max_length=255, blank=True, null=True)
    liquor_bowner_marktd = models.CharField(max_length=255, blank=True, null=True)
    label_dimension = models.CharField(max_length=255, blank=True, null=True)
    bottling_fee_per_case = models.SmallIntegerField(blank=True, null=True)
    import_fee_per_case = models.SmallIntegerField(blank=True, null=True)
    export_fee_per_case = models.SmallIntegerField(blank=True, null=True)
    min_mrp_per_bottle = models.SmallIntegerField(blank=True, null=True)
    max_mrp_per_bottle = models.IntegerField(blank=True, null=True)
    exdist_price_per_bottle = models.DecimalField(max_digits=15, decimal_places=4, blank=True, null=True)
    excise_duty_per_bottle = models.DecimalField(max_digits=15, decimal_places=4, blank=True, null=True)
    bottling_fee_per_bottle = models.DecimalField(max_digits=15, decimal_places=4, blank=True, null=True)
    import_fee_per_bottle = models.DecimalField(max_digits=15, decimal_places=4, blank=True, null=True)
    export_fee_per_bottle = models.DecimalField(max_digits=15, decimal_places=4, blank=True, null=True)
    mono_carton_flag = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'master_liquor_product'
        managed = False

    def __str__(self):
        return f"{self.liquor_brand_code} — {self.liquor_product_reg_no or 'No Reg No'}"


# ---------------------------------------------------------------------------
# MM_Liquor_Category  →  master_liquor_category
# ---------------------------------------------------------------------------

class LiquorCategory(models.Model):
    """
    Lookup table for liquor category.
    """
    liquor_cat_code = models.PositiveSmallIntegerField(primary_key=True)
    liquor_cat_desc = models.CharField(max_length=100)
    liquor_cat_abbr = models.CharField(max_length=10)
    delete_status = models.CharField(max_length=1, default='N')

    class Meta:
        db_table = 'master_liquor_category'
        managed = False
        ordering = ['liquor_cat_code']

    def __str__(self):
        return f"{self.liquor_cat_abbr} — {self.liquor_cat_desc}"


# ---------------------------------------------------------------------------
# MM_Liquor_Type  →  master_liquor_type_details
# ---------------------------------------------------------------------------

class LiquorType(models.Model):
    """
    Lookup table for liquor type details (Whisky, Beer, Rum, etc.)
    under a category and kind.
    """
    id = models.BigAutoField(primary_key=True)
    liquor_cat = models.PositiveSmallIntegerField(db_column='liquor_cat_code')
    liquor_kind = models.ForeignKey(
        LiquorKind,
        on_delete=models.PROTECT,
        related_name='types',
        db_column='liquor_kind_id',
    )
    liquor_type_code = models.PositiveSmallIntegerField()
    liquor_type_desc = models.CharField(max_length=100)
    liquor_type_code_old = models.CharField(max_length=20, blank=True, null=True)
    delete_status = models.CharField(max_length=1, default='N')

    class Meta:
        db_table = 'master_liquor_type_details'
        managed = False
        ordering = ['liquor_cat', 'liquor_kind', 'liquor_type_code']
        unique_together = [('liquor_cat', 'liquor_kind', 'liquor_type_code')]

    def __str__(self):
        return f"{self.liquor_type_desc} ({self.liquor_type_code})"


# ---------------------------------------------------------------------------
# master_Brand_owner
# ---------------------------------------------------------------------------

class master_Brand_owner(models.Model):
    Liquor_BOwner_Origin = models.CharField(max_length=10, blank=True, null=True)
    Liquor_BOwner_Code = models.CharField(max_length=50, primary_key=True)
    Liquor_BOwner_Country = models.CharField(max_length=100, blank=True, null=True)
    Liquor_BOwner_State = models.CharField(max_length=100, blank=True, null=True)
    Liquor_BOwner_Name = models.CharField(max_length=255, blank=True, null=True)
    Liquor_BOwner_Address = models.TextField(blank=True, null=True)
    Liquor_BOwner_PinCode = models.CharField(max_length=20, blank=True, null=True)
    Licensee_id_no = models.CharField(max_length=50, blank=True, null=True)
    Entry_Flag = models.CharField(max_length=10, blank=True, null=True)
    Merged_Flag = models.CharField(max_length=10, blank=True, null=True)
    Merged_Liquor_BOwner_Code = models.CharField(max_length=50, blank=True, null=True)
    Delete_Status = models.CharField(max_length=10, default='N')
    Brand_Owner_Type_Code = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = 'master_brand_owner_table'
        ordering = ['Liquor_BOwner_Code']
        verbose_name = 'master Brand owner'
        verbose_name_plural = 'master Brand owner'

    def __str__(self):
        return f"{self.Liquor_BOwner_Code} — {self.Liquor_BOwner_Name}"




