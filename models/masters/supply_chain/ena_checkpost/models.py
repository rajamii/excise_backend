from django.db import models

class Checkpost(models.Model):
    check_post_id = models.AutoField(primary_key=True)
    check_post_name=models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.check_post_name

    class Meta:
        db_table = 'ena_check_post_details'
        ordering = ['check_post_id']
