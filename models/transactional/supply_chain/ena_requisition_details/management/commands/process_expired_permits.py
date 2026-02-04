from django.core.management.base import BaseCommand
from django.db import connection, transaction
import time

class Command(BaseCommand):
    help = 'Executes the copy_expired_permits SQL function to expire permits.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true', help='Run in a continuous loop')
        parser.add_argument('--interval', type=int, default=10, help='Interval in seconds for loop mode')

    def handle(self, *args, **options):
        loop = options['loop']
        interval = options['interval']

        if loop:
            self.stdout.write(self.style.SUCCESS(f'Starting expiration loop every {interval} seconds...'))
            while True:
                self.run_sql()
                time.sleep(interval)
        else:
            self.run_sql()
            self.stdout.write(self.style.SUCCESS('Successfully executed copy_expired_permits()'))

    def run_sql(self):
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT public.copy_expired_permits();")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error executing SQL: {e}'))
