from django.apps import AppConfig
import threading
import time
import os
import logging
from django.db import connection, transaction
from django.conf import settings

logger = logging.getLogger(__name__)

def run_expiry_loop():
    """
    Background thread that runs indefinitely.
    Checks for expired permits every 10 seconds (for testing).
    """
    interval_seconds = 10
    try:
        interval_seconds = max(1, int(os.environ.get('PERMIT_EXPIRY_LOOP_INTERVAL_SECONDS', '10')))
    except ValueError:
        interval_seconds = 10

    logger.info("Permit expiry scheduler thread started (interval_seconds=%s)", interval_seconds)

    while True:
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT public.copy_expired_permits();")
        except Exception as e:
            logger.exception("Permit expiry scheduler error")
        
        time.sleep(interval_seconds)

class EnaRequisitionDetailsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'models.transactional.supply_chain.ena_requisition_details'
    verbose_name = 'ena_requisition_details'

    def ready(self):
        scheduler_enabled = os.environ.get('ENABLE_PERMIT_EXPIRY_SCHEDULER', '').strip().lower()
        scheduler_disabled = scheduler_enabled in {'0', 'false', 'no'}

        # In local development, keep the old automation behavior unless explicitly disabled.
        # In non-debug environments, require an explicit opt-in.
        should_run = (
            not scheduler_disabled and (
                scheduler_enabled in {'1', 'true', 'yes'} or settings.DEBUG
            )
        )
        if not should_run:
            return

        # In local runserver, only run in the main worker process, not the autoreloader helper.
        # In hosted/non-debug environments RUN_MAIN is usually unset, so allow explicit opt-in.
        is_dev_autoreload_main = os.environ.get('RUN_MAIN') == 'true'
        if settings.DEBUG and not is_dev_autoreload_main:
            return

        t = threading.Thread(target=run_expiry_loop, daemon=True)
        t.start()
        logger.info("Permit expiry scheduler activated")

