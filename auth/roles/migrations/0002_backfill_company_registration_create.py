from django.db import migrations

def backfill_company_registration_permissions(apps, schema_editor):
    Role = apps.get_model('roles', 'Role')
    roles_to_update = []
    
    for role in Role.objects.all():
        # Safely fetch array fields (fallback to empty list if None)
        can_view = role.can_view or []
        can_add = role.can_add or []
        
        # Normalize labels to catch variations like 'company-registration'
        view_labels = [str(l).strip().lower().replace('-', '_') for l in can_view]
        add_labels = [str(l).strip().lower().replace('-', '_') for l in can_add]
        
        # If the role can view company_registration but cannot explicitly add it, backfill it
        if 'company_registration' in view_labels and 'company_registration' not in add_labels:
            # We append the clean string to the actual model field
            role.can_add.append('company_registration')
            roles_to_update.append(role)
            
    if roles_to_update:
        # Perform a bulk update to efficiently save changes to the database
        Role.objects.bulk_update(roles_to_update, ['can_add'])

def reverse_backfill(apps, schema_editor):
    """
    Optional reverse operation if you ever need to rollback this specific migration.
    Note: Reversing this might remove legitimate 'create' permissions added manually later, 
    so RunPython.noop is also a safe alternative.
    """
    pass

class Migration(migrations.Migration):

    dependencies = [
        # Make sure this points to your latest existing roles migration
        ('roles', '0001_initial'), 
    ]

    operations = [
        migrations.RunPython(
            backfill_company_registration_permissions, 
            reverse_code=reverse_backfill
        ),
    ]