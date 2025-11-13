from django.db import models

class Purpose(models.Model):
    purpose_name = models.CharField(max_length=200)
  

    def __str__(self):
        return self.purpose_name

    class Meta:
        db_table = 'purpose'
        ordering = ['purpose_name']
