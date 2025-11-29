import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

with connection.cursor() as cursor:
    print("Dropping strength_from...")
    cursor.execute("ALTER TABLE ena_requisition_detail DROP COLUMN strength_from")
    print("Dropping strength_to...")
    cursor.execute("ALTER TABLE ena_requisition_detail DROP COLUMN strength_to")
    print("Done.")
