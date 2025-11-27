from django.db import models

class Checkpost(models.Model):
    checkpost_name=models.CharField(max_length=100)
    def __str__(self):
        return self.checkpost_name

    class Meta:
        db_table = 'checkpost'
        ordering = ['checkpost_name']
