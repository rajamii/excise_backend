from django.contrib import admin
from auth.user.models import SMSServiceConfig


@admin.register(SMSServiceConfig)
class SMSServiceConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "username", "signature", "dlt_entity_id", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "username", "signature", "dlt_entity_id", "dlt_template_id")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Gateway Credentials",
            {
                "fields": (
                    "name",
                    "is_active",
                    "username",
                    "pin",
                    "signature",
                    "dlt_entity_id",
                    "dlt_template_id",
                )
            },
        ),
        (
            "Transport",
            {"fields": ("base_url", "verify_ssl", "timeout_seconds")},
        ),
        (
            "Message",
            {"fields": ("message_template",)},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at")},
        ),
    )
