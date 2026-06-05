from django.core.management.base import BaseCommand
from models.masters.license.views import deactivate_all_expired_licenses

class Command(BaseCommand):
    help = "Find and deactivate all expired licenses globally and reset their payment flags."

    def handle(self, *args, **options):
        self.stdout.write("Checking and deactivating expired licenses...")
        try:
            deactivate_all_expired_licenses()
            self.stdout.write(self.style.SUCCESS("Successfully processed expired licenses."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error during deactivation: {str(e)}"))
