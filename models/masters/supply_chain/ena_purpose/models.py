from django.db import models

class Purpose(models.Model):
    purpose_id = models.AutoField(primary_key=True)
    purpose_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
  

    def __str__(self):
        return self.purpose_name

    class Meta:
        db_table = 'ena_purpose_details'
        ordering = ['purpose_name']
