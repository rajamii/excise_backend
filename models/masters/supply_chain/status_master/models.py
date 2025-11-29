from django.db import models

class StatusMaster(models.Model):
    status_id = models.AutoField(primary_key=True)
    status_code = models.CharField(max_length=50, unique=True)
    status_name = models.CharField(max_length=100)

    class Meta:
        db_table = 'status_master'
        verbose_name = 'Status Master'
        verbose_name_plural = 'Status Masters'
        managed = False # User said table already exists

    def __str__(self):
        return f"{self.status_name} ({self.status_code})"
