from django.db import models


class SyncRecord(models.Model):
    """
    Tracks sync status for master data records shared with LMSDB.
    entity_type: 'factory' | 'liquor_type' | 'brand' | 'bottle_type' | 'bottle_size'
    entity_id: the PK of the related record
    is_sync: 0 = pending sync, 1 = synced by LMSDB
    """
    ENTITY_CHOICES = [
        ('factory', 'Factory'),
        ('liquor_type', 'Liquor Type'),
        ('brand', 'Brand'),
        ('bottle_type', 'Bottle Type'),
        ('bottle_size', 'Bottle Size'),
    ]

    entity_type = models.CharField(max_length=20, choices=ENTITY_CHOICES)
    entity_id = models.IntegerField()
    is_sync = models.IntegerField(default=0)  # 0 = unsynced, 1 = synced
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'lmsdb_sync_records'
        unique_together = ('entity_type', 'entity_id')

    def __str__(self):
        return f"{self.entity_type}:{self.entity_id} sync={self.is_sync}"
