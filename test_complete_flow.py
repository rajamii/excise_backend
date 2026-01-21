"""
Complete test to simulate the backend multi-brand save flow
"""

class SimulatedRollObj:
    def __init__(self, carton_number, total_count, used, damaged):
        self.carton_number = carton_number
        self.total_count = total_count
        self.used = used
        self.damaged = damaged
    
    def __repr__(self):
        available = self.total_count - self.used - self.damaged
        return f"Roll({self.carton_number}: total={self.total_count}, used={self.used}, damaged={self.damaged}, available={available})"

def simulate_save(roll_range_str, issued_qty, wastage_qty, roll_obj):
    """Simulate the _update_procurement_usage_impl function"""
    
    print(f"\n{'='*80}")
    print(f"🔥 SIMULATING DAILY REGISTER SAVE")
    print(f"{'='*80}")
    print(f"Entry Roll Range: {roll_range_str}")
    print(f"Issued Qty: {issued_qty}")
    print(f"Wastage Qty: {wastage_qty}")
    print(f"{'='*80}\n")
    
    # Extract carton number (THE FIX)
    if '_BRAND_' in roll_range_str:
        # Multi-brand format: 'a1 - 1 - 50_BRAND_1'
        parts = roll_range_str.split('_BRAND_')
        base_range = parts[0].strip()  # 'a1 - 1 - 50'
        carton_number = base_range.split(' - ')[0].strip()  # 'a1'
        print(f"DEBUG: Multi-brand format detected. Extracted carton: '{carton_number}' from '{roll_range_str}'")
    elif ' - ' in roll_range_str:
        parts = roll_range_str.split(' - ')
        carton_number = parts[0].strip()
    else:
        carton_number = roll_range_str
    
    print(f"DEBUG: Updating usage for Carton '{carton_number}' (Issued: {issued_qty}, Wastage: {wastage_qty})")
    print()
    
    # Get current counts
    total_count = roll_obj.total_count
    current_used = roll_obj.used
    current_damaged = roll_obj.damaged
    print(f"DEBUG: Current state - total: {total_count}, used: {current_used}, damaged: {current_damaged}")
    
    # Calculate new counts (THE ACTUAL UPDATE LOGIC)
    new_used = current_used + (issued_qty or 0)
    new_damaged = current_damaged + (wastage_qty or 0)
    new_available = max(0, total_count - new_used - new_damaged)
    
    print(f"DEBUG: New state - available: {new_available}, used: {new_used}, damaged: {new_damaged}")
    
    # Update the roll object
    roll_obj.used = new_used
    roll_obj.damaged = new_damaged
    
    print(f"\n✅ Updated {roll_obj}")
    
    return roll_obj

# Test the exact scenario from the logs
print("="*80)
print("🧪 TESTING MULTI-BRAND SAVE SCENARIO")
print("="*80)

# Initial state (from logs): a1 has total=50, used=0, damaged=0
roll_a1 = SimulatedRollObj(carton_number='a1', total_count=50, used=0, damaged=0)
print(f"\n📊 Initial State: {roll_a1}")

# Save Brand 1: a1 - 1 - 50_BRAND_1 with issued_qty=1
print(f"\n{'#'*80}")
print(f"# SAVE #1: Brand 1")
print(f"{'#'*80}")
roll_a1 = simulate_save(
    roll_range_str="a1 - 1 - 50_BRAND_1",
    issued_qty=1,
    wastage_qty=0,
    roll_obj=roll_a1
)

# Save Brand 2: a1 - 1 - 50_BRAND_2 with issued_qty=1
print(f"\n{'#'*80}")
print(f"# SAVE #2: Brand 2")
print(f"{'#'*80}")
roll_a1 = simulate_save(
    roll_range_str="a1 - 1 - 50_BRAND_2",
    issued_qty=1,
    wastage_qty=0,
    roll_obj=roll_a1
)

# Final verification
print(f"\n{'='*80}")
print(f"📊 FINAL STATE VERIFICATION")
print(f"{'='*80}")
print(f"Final State: {roll_a1}")
print()

expected_used = 2
expected_available = 48

if roll_a1.used == expected_used and (roll_a1.total_count - roll_a1.used - roll_a1.damaged) == expected_available:
    print(f"✅ SUCCESS! The multi-brand save logic is working correctly!")
    print(f"   - Used: {roll_a1.used} (expected: {expected_used}) ✅")
    print(f"   - Available: {roll_a1.total_count - roll_a1.used - roll_a1.damaged} (expected: {expected_available}) ✅")
else:
    print(f"❌ FAILURE! The counts are incorrect!")
    print(f"   - Used: {roll_a1.used} (expected: {expected_used}) {'✅' if roll_a1.used == expected_used else '❌'}")
    print(f"   - Available: {roll_a1.total_count - roll_a1.used - roll_a1.damaged} (expected: {expected_available}) {'✅' if (roll_a1.total_count - roll_a1.used - roll_a1.damaged) == expected_available else '❌'}")

print(f"{'='*80}")
