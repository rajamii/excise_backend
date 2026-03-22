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
        ordering = ['brand_owner_code']
        indexes = [
            models.Index(fields=['brand_owner_name'], name='mbo_name_idx'),
            models.Index(fields=['brand_owner_type'], name='mbo_type_idx'),
            models.Index(fields=['enable_status'],    name='mbo_status_idx'),
        ]

    def __str__(self):
        return f"{self.brand_owner_code} — {self.brand_owner_name}"


# ---------------------------------------------------------------------------
# MM_Liquor_Category  →  master_liquor_category
# ---------------------------------------------------------------------------

class LiquorCategory(models.Model):
    """
    Top-level liquor classification: Country Liquor, Foreign Liquor, Beer, Homemade.
    """
    liquor_cat_code = models.PositiveSmallIntegerField(primary_key=True)
    liquor_cat_desc = models.CharField(max_length=100)
    liquor_cat_abbr = models.CharField(max_length=10)
    delete_status = models.CharField(max_length=1, default='N')

    class Meta:
        db_table = 'master_liquor_category'
        ordering = ['liquor_cat_code']

    def __str__(self):
        return f"{self.liquor_cat_abbr} — {self.liquor_cat_desc}"


# ---------------------------------------------------------------------------
# MM_Liquor_Kind  →  master_liquor_kind
# ---------------------------------------------------------------------------

class LiquorKind(models.Model):
    """
    Sub-classification within a category: IMFL, OSBI, Beer, etc.
    Composite PK: (liquor_cat_code, liquor_kind_code).
    """
    liquor_cat = models.ForeignKey(
        LiquorCategory,
        on_delete=models.PROTECT,
        related_name='kinds',
        db_column='liquor_cat_code',
    )
    liquor_kind_code = models.PositiveSmallIntegerField()
    liquor_kind_desc = models.CharField(max_length=100)
    liquor_kind_abbr = models.CharField(max_length=20)
    delete_status = models.CharField(max_length=1, default='N')

    class Meta:
        db_table = 'master_liquor_kind'
        unique_together = [('liquor_cat', 'liquor_kind_code')]
        ordering = ['liquor_cat', 'liquor_kind_code']

    def __str__(self):
        return f"{self.liquor_kind_abbr} — {self.liquor_kind_desc}"


# ---------------------------------------------------------------------------
# MM_Liquor_Type  →  master_liquor_type
# ---------------------------------------------------------------------------

class LiquorType(models.Model):
    """
    Specific liquor type within a kind: Whisky, Rum, Beer, Wine, etc.
    Composite PK: (liquor_cat_code, liquor_kind_code, liquor_type_code).
    """
    liquor_cat = models.ForeignKey(
        LiquorCategory,
        on_delete=models.PROTECT,
        related_name='types',
        db_column='liquor_cat_code',
    )
    liquor_kind = models.ForeignKey(
        LiquorKind,
        on_delete=models.PROTECT,
        related_name='types',
        db_column='liquor_kind_id',
    )
    liquor_type_code = models.PositiveSmallIntegerField()
    liquor_type_desc = models.CharField(max_length=100)
    liquor_type_code_old = models.PositiveSmallIntegerField(blank=True, null=True)
    delete_status = models.CharField(max_length=1, default='N')

    class Meta:
        db_table = 'master_liquor_type'
        unique_together = [('liquor_cat', 'liquor_kind', 'liquor_type_code')]
        ordering = ['liquor_cat', 'liquor_kind', 'liquor_type_code']

    def __str__(self):
        return f"{self.liquor_type_desc}"


# ---------------------------------------------------------------------------
# MM_Liquor_Brand  →  master_liquor_brand
# ---------------------------------------------------------------------------

class LiquorBrand(models.Model):
    """
    Individual brand registered under a liquor type.
    liquor_brand_code is the natural PK (e.g. 2013/0002).
    """
    liquor_brand_code = models.CharField(max_length=20, primary_key=True)
    liquor_cat = models.ForeignKey(
        LiquorCategory,
        on_delete=models.PROTECT,
        related_name='brands',
        db_column='liquor_cat_code',
    )
    liquor_kind = models.ForeignKey(
        LiquorKind,
        on_delete=models.PROTECT,
        related_name='brands',
        db_column='liquor_kind_id',
    )
    liquor_type = models.ForeignKey(
        LiquorType,
        on_delete=models.PROTECT,
        related_name='brands',
        db_column='liquor_type_id',
    )
    liquor_brand_desc = models.CharField(max_length=255)
    brand_name_alias = models.CharField(max_length=20, blank=True, null=True)
    liquor_type_code_old = models.CharField(max_length=20, blank=True, null=True)
    entry_flag = models.CharField(max_length=10, blank=True, null=True)
    delete_status = models.CharField(max_length=1, default='N')

    class Meta:
        db_table = 'master_liquor_brand'
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
        ordering = ['-from_date']

    def __str__(self):
        return f"Fee: reg={self.registration_fee} collab={self.collaboration_fees} deposit={self.security_deposit}"
