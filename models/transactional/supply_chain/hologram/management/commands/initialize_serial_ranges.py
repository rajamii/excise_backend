from django.core.management.base import BaseCommand
from models.transactional.supply_chain.hologram.models import HologramRollsDetails, HologramSerialRange

class Command(BaseCommand):
    help = 'Initialize HologramSerialRange entries for existing rolls that don\'t have them'

    def handle(self, *args, **options):
        rolls = HologramRollsDetails.objects.all()
        total = rolls.count()
        
        self.stdout.write(f"Processing {total} rolls...")
        
        initialized = 0
        skipped = 0
        
        for roll in rolls:
            # Check if this roll already has serial ranges
            existing_ranges = HologramSerialRange.objects.filter(roll=roll).count()
            
            if existing_ranges > 0:
                skipped += 1
                continue
            
            # Create initial AVAILABLE range for the entire roll
            if roll.from_serial and roll.to_serial and roll.total_count > 0:
                HologramSerialRange.objects.create(
                    roll=roll,
                    from_serial=roll.from_serial,
                    to_serial=roll.to_serial,
                    count=roll.total_count,
                    status='AVAILABLE',
                    description=f'Initial range for roll {roll.carton_number}'
                )
                
                # Update available_range field
                roll.update_available_range()
                
                initialized += 1
                self.stdout.write(f"✅ Initialized {roll.carton_number}: {roll.from_serial}-{roll.to_serial}")
        
        self.stdout.write(self.style.SUCCESS(f"\n✅ Complete! Initialized: {initialized}, Skipped: {skipped}"))
