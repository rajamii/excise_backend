import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

with connection.cursor() as cursor:
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'ena_requisition_detail'")
    columns = [row[0] for row in cursor.fetchall()]
    print("Columns:")
    for col in columns:
        print(col)
