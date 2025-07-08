from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from typing import TYPE_CHECKING

User = get_user_model()

class UserActivity(models.Model):
    class ActivityType(models.TextChoices):
        REGISTRATION = 'REG', 'Registration'
        LOGIN = 'LOGIN', 'Login'
        LOGOUT = 'LOGOUT', 'Logout'
        PASSWORD_RESET = 'PASS_RESET', 'Password Reset'
        USER_UPDATE = 'USR_UPD', 'User Profile Update'  # Added
        USER_DELETE = 'USR_DEL', 'User Account Deletion' # Added
        # Add other activity types as needed

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='activities',
        help_text="The user who performed the activity."
    )
    # New field to track the user whose profile was affected by the activity
    target_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL, # If the target user is deleted, set this to NULL
        null=True,
        blank=True,
        related_name='targeted_activities',
        help_text="The user whose profile was affected by the activity (e.g., updated or deleted)."
    )
    activity_type = models.CharField(
        max_length=20,
        choices=ActivityType.choices
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    device_id = models.CharField(max_length=255, null=True, blank=True)
    location = models.CharField(max_length=100, null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)

    if TYPE_CHECKING:
        def get_activity_type_display(self) -> str: ...  # Type hint for Django's auto-generated method
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'User Activities'
        indexes = [
            models.Index(fields=['user', 'activity_type']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['target_user', 'activity_type']), # Added index for target_user
        ]

    def __str__(self):
        # Improved __str__ to reflect the target_user when applicable
        if self.target_user and self.user != self.target_user:
            return f"{self.user.email} - {self.get_activity_type_display()} on {self.target_user.email} at {self.timestamp}"
        return f"{self.user.email} - {self.get_activity_type_display()} at {self.timestamp}"
