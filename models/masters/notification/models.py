from django.db import models
from django.core.exceptions import ValidationError
import re


def validate_notification_subject(value):
    if not re.match(r'^[a-zA-Z0-9\s\-/.,()&]*$', value):
        raise ValidationError(
            f'{value} is not a valid subject. Only letters, numbers, spaces, hyphens, slashes, dots, commas, parentheses, and ampersands are allowed.'
        )


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
        upload_to='notifications/',
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
