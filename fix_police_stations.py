#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from django.db import connection
from models.masters.core.models import District

print("Fixing PoliceStation records with NULL district_code...")

# Get all districts (should at least have one)
districts = District.objects.filter(is_active=True)
print(f"Found {districts.count()} active districts")

if districts.count() > 0:
    default_district = districts.first()
    print(f"Using default district: {default_district.district} (code: {default_district.district_code})")
    
    # Update NULL district_code to the default
    with connection.cursor() as cursor:
        cursor.execute("""
            UPDATE masters_policestation 
            SET district_code = %s 
            WHERE district_code IS NULL
        """, [default_district.district_code])
        
        print(f"Updated {cursor.rowcount} records")
else:
    print("No active districts found. Please create at least one district first.")
