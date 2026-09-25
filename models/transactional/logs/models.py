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


class AdminLog(models.Model):
    """
    Audit log table ('admin_log') tracking all actions performed by administrators
    and users across every module of the system.

    Maintains immutable direct snapshots of user identity (admin_id, username, full_name, role)
    so historical records are never lost even if the user account is deleted, deactivated,
    or altered.
    """
    # ── Direct Identity Snapshots ──────────────────────────────────────────
    admin_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Direct snapshot of the admin/user ID at the time of action."
    )
    username = models.CharField(
        max_length=150,
        db_index=True,
        help_text="Snapshot of the admin/user username at the time of action."
    )
    full_name = models.CharField(
        max_length=255,
        help_text="Snapshot of the admin/user full name (or designation) at the time of action."
    )
    role = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Snapshot of the role/designation (e.g. Commissioner, Joint Commissioner, OIC Admin, etc.)."
    )

    # Optional loose foreign key (set to NULL if the user is deleted)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admin_audit_logs',
        help_text="Optional relational link to the user account. Direct identity snapshot columns preserve history."
    )

    # ── Target Module & Application ────────────────────────────────────────
    module_name = models.CharField(
        max_length=150,
        db_index=True,
        help_text="Module name (e.g. ENA Bulk Requisition, Revalidation, Cancellation, Hologram Procurement, etc.)."
    )
    application_id = models.CharField(
        max_length=150,
        db_index=True,
        help_text="Application / Request / Reference number of the target object."
    )
    content_type = models.ForeignKey(
        'contenttypes.ContentType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Polymorphic content type of the target object."
    )
    object_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Primary key of the target object."
    )

    # ── Action & Workflow Progression ──────────────────────────────────────
    action = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Action performed (e.g. APPROVE, REJECT, OBJECTION, REVERT, FORWARD, VERIFY, CANCEL, UPDATE, ISSUE, etc.)."
    )
    from_stage = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        help_text="Stage / status before the action was executed."
    )
    to_stage = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        help_text="Stage / status after the action was executed."
    )
    to_stage_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Human-readable name of the target stage."
    )
    to_stage_user_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Direct snapshot of the ID of the admin/user to whom the application was forwarded in the next stage."
    )
    to_stage_username = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        db_index=True,
        help_text="Username of the admin/user to whom the application was forwarded in the next stage."
    )
    to_stage_full_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Full name of the admin/user to whom the application was forwarded in the next stage."
    )
    status = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Status summary or outcome of the action."
    )

    remarks = models.TextField(
        null=True,
        blank=True,
        help_text="Exact remarks, comments, objection details, or rejection reasons entered by the admin."
    )

    # ── Revert Action Details ──────────────────────────────────────────────
    reverted_by_id = models.CharField(max_length=100, null=True, blank=True)
    reverted_by_username = models.CharField(max_length=150, null=True, blank=True)
    reverted_by_name = models.CharField(max_length=255, null=True, blank=True)
    reverted_by_role = models.CharField(max_length=100, null=True, blank=True)

    reverted_to_id = models.CharField(max_length=100, null=True, blank=True)
    reverted_to_username = models.CharField(max_length=150, null=True, blank=True)
    reverted_to_name = models.CharField(max_length=255, null=True, blank=True)
    reverted_to_role = models.CharField(max_length=100, null=True, blank=True)
    reverted_to_stage = models.CharField(max_length=150, null=True, blank=True)

    # ── Audit Metadata & Timestamp ─────────────────────────────────────────
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional structured context (e.g., objection item list, field diffs, payload details)."
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Exact date and time when the action took place."
    )

    class Meta:
        db_table = 'admin_log'
        ordering = ['-timestamp']
        verbose_name = 'Admin Audit Log'
        verbose_name_plural = 'Admin Audit Logs'
        indexes = [
            models.Index(fields=['module_name', 'application_id']),
            models.Index(fields=['username', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['role', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.username} ({self.role}) - {self.action} on {self.module_name} ({self.application_id})"

