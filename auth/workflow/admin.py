from django.contrib import admin
from .models import Transaction, Objection, Rejection

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('application', 'stage', 'performed_by', 'timestamp')
    list_filter = ('stage', 'content_type')

@admin.register(Objection)
class ObjectionAdmin(admin.ModelAdmin):
    list_display = ('application', 'field_name', 'is_resolved', 'raised_on')

@admin.register(Rejection)
class RejectionAdmin(admin.ModelAdmin):
    list_display = ('application', 'stage', 'rejected_by', 'rejected_on')
    list_filter = ('stage', 'content_type')