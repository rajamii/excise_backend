
from transactional.supply_chain.hologram.models import HologramProcurement, HologramRollsDetails

def fix_hologram_data():
    print("🚀 Starting Hologram Data Repair...")
    
    procurements = HologramProcurement.objects.all()
    total_fixed = 0
    
    for proc in procurements:
        # print(f"Checking Procurement: {proc.ref_no} (ID: {proc.id})")
        
        details = proc.carton_details or []
        updated = False
        
        for detail in details:
            c_num = detail.get('cartoonNumber') or detail.get('cartoon_number')
            if not c_num:
                continue
                
            try:
                # Find the source of truth
                roll_obj = HologramRollsDetails.objects.get(
                    procurement=proc,
                    carton_number=c_num
                )
                
                # Check for discrepancies
                json_avail = detail.get('available_qty')
                json_used = detail.get('used_qty')
                json_status = detail.get('status')
                
                # Force status update if count doesn't match status
                # e.g. if Available > 0 but Status is IN_USE (and no IN_USE ranges), it should be AVAILABLE
                # ... but let's trust DB fields for now
                
                db_avail = roll_obj.available
                db_used = roll_obj.used
                db_status = roll_obj.status
                
                # If discrepancies found, update JSON
                # We trust DB more than JSON for status and counts
                if json_avail != db_avail or json_used != db_used: # or json_status != db_status:
                    print(f"  ⚠️  Mismatch for {c_num}:")
                    print(f"      JSON: Avail={json_avail}, Used={json_used}, Status={json_status}")
                    print(f"      DB:   Avail={db_avail}, Used={db_used}, Status={db_status}")
                    
                    detail['available_qty'] = db_avail
                    detail['used_qty'] = db_used
                    detail['damaged_qty'] = roll_obj.damaged
                    detail['status'] = db_status
                    
                    updated = True
                    total_fixed += 1
                    
            except HologramRollsDetails.DoesNotExist:
                # print(f"  ❌ No HologramRollsDetails found for {c_num}")
                pass
                
        if updated:
            proc.carton_details = details
            proc.save(update_fields=['carton_details'])
            print(f"✅ Saved updates for Procurement {proc.ref_no}")
            
    print(f"\n🎉 Repair Complete! Fixed {total_fixed} carton entries.")

# Run immediately
fix_hologram_data()
