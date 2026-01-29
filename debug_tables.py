
import os
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from django.db import connection

def list_tables():
    with connection.cursor() as cursor:
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
        tables = [row[0] for row in cursor.fetchall()]
        print("Existing tables:")
        for t in tables:
            print(f"- {t}")

if __name__ == "__main__":
    list_tables()
