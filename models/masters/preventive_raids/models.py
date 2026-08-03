from django.db import models
from django.utils import timezone

from utils.file_validation import secure_upload_filename


def upload_preventive_raid_image_path(instance, filename):
    return secure_upload_filename(filename, 'preventive_raids/images')


class PreventiveRaid(models.Model):
    title = models.CharField(max_length=500)
    subject = models.TextField(blank=True, null=True)
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'masters_preventiveraid'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return self.title


class PreventiveRaidImage(models.Model):
    raid = models.ForeignKey(PreventiveRaid, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to=upload_preventive_raid_image_path, max_length=500)

    class Meta:
        db_table = 'masters_preventiveraidimage'

    def __str__(self):
        return f"Image for {self.raid.title}"
