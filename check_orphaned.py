#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from django.db import connection

print("Checking for orphaned PoliceStation records...")
with connection.cursor() as cursor:
    # Check records where district_code is NULL
    cursor.execute("""
        SELECT COUNT(*) FROM masters_policestation WHERE district_code IS NULL
    """)
    null_count = cursor.fetchone()[0]
    print(f"Records with NULL district_code: {null_count}")
    
    # Check records where district_code doesn't exist in District table
    cursor.execute("""
        SELECT COUNT(*) FROM masters_policestation ps
        WHERE district_code IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM masters_district d WHERE d.district_code = ps.district_code
        )
    """)
    orphaned_count = cursor.fetchone()[0]
    print(f"Records with non-existent district_code: {orphaned_count}")
    
    if orphaned_count > 0:
        print("\nOrphaned records:")
        cursor.execute("""
            SELECT id, police_station, district_code FROM masters_policestation ps
            WHERE district_code IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM masters_district d WHERE d.district_code = ps.district_code
            )
            LIMIT 10
        """)
        for row in cursor.fetchall():
            print(f"  ID: {row[0]}, Police Station: {row[1]}, District Code: {row[2]}")
