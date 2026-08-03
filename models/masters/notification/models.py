from django.db import models
from django.core.exceptions import ValidationError
import re

from utils.file_validation import secure_upload_filename, validate_uploaded_file


def validate_notification_subject(value):
    if not re.match(r'^[a-zA-Z0-9\s\-/.,()&]*$', value):
        raise ValidationError(
            f'{value} is not a valid subject. Only letters, numbers, spaces, hyphens, slashes, dots, commas, parentheses, and ampersands are allowed.'
        )


def upload_notification_file_path(instance, filename):
    return secure_upload_filename(filename, 'notifications')


'''
    Model: Notification
    Stores public notification / act / rule / circular details
'''

class Notification(models.Model):
    NOTIFICATION_CATEGORY_CHOICES = [
        ('act', 'Act'),
        ('rule', 'Rule'),
        ('circular', 'Circular'),
    ]

    subject = models.CharField(max_length=255, validators=[validate_notification_subject])
    category = models.CharField(max_length=20, choices=NOTIFICATION_CATEGORY_CHOICES)
    notification_date = models.DateField()
    notification_file = models.FileField(
        upload_to=upload_notification_file_path,
        max_length=500,
        null=True,
        blank=True
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'masters_notification'
        ordering = ['-notification_date', '-id']

    def __str__(self):
        return f"{self.subject} ({self.notification_date})"

    def clean(self):
        super().clean()
        validate_uploaded_file(
            self.notification_file,
            allowed_extensions=['jpeg', 'jpg', 'pdf'],
            allowed_mime_types=['image/jpeg', 'application/pdf'],
            max_size_bytes=2 * 1024 * 1024,
            field_label='Notification file'
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
