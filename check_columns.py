#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from django.db import connection

print("Checking columns in masters_policestation table...")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name='masters_policestation'
        ORDER BY ordinal_position
    """)
    columns = cursor.fetchall()
    print("\nColumns found:")
    for col_name, data_type in columns:
        print(f"  - {col_name}: {data_type}")
    
    if any(col[0] == 'district_code' for col in columns):
        print("\n✓ district_code column EXISTS")
    else:
        print("\n✗ district_code column MISSING")
