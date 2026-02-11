from django.apps import AppConfig
import threading
import time
import os
import sys
from django.db import connection, transaction

def run_expiry_loop():
    """
    Background thread that runs indefinitely.
    Checks for expired permits every 10 seconds (for testing).
    """
    print(" [Scheduler] Thread Started. Checking every 10s...")
    while True:
        try:
            # print(" [Scheduler] Ticking...")
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT public.copy_expired_permits();")
            # print(" [Scheduler] Tick Success.")
        except Exception as e:
            print(f" [Scheduler] Error: {e}")
        
        # Sleep for 10 seconds
        time.sleep(10)

class EnaRequisitionDetailsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'models.transactional.supply_chain.ena_requisition_details'
    verbose_name = 'ena_requisition_details'

    def ready(self):
        # Only run in the main worker process, not the reloader
        if os.environ.get('RUN_MAIN') == 'true':
            # Check if thread is already alive (unlikely in fresh process, but good practice)
            # For simplicity, we just start it.
            t = threading.Thread(target=run_expiry_loop, daemon=True)
            t.start()
            print(" >> Excise Automation: Expiry Scheduler ACTIVATED << ")

