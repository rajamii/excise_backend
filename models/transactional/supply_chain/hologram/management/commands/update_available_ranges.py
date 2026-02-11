from django.core.management.base import BaseCommand
from models.transactional.supply_chain.hologram.models import HologramRollsDetails

class Command(BaseCommand):
    help = 'Update available_range field for all hologram rolls'

    def handle(self, *args, **options):
        rolls = HologramRollsDetails.objects.all()
        total = rolls.count()
        
        self.stdout.write(f"Updating available_range for {total} rolls...")
        
        updated = 0
        for roll in rolls:
            roll.update_available_range()
            updated += 1
            if updated % 10 == 0:
                self.stdout.write(f"  Progress: {updated}/{total}")
        
        self.stdout.write(self.style.SUCCESS(f"✅ Successfully updated {updated} rolls"))
