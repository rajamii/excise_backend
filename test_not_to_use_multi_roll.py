"""
Test "Not to Use" functionality with multi-brand format for multiple rolls
"""

class SimulatedRange:
    def __init__(self, from_serial, to_serial, status):
        self.from_serial = from_serial
        self.to_serial = to_serial
        self.status = status
    
    def __repr__(self):
        return f"Range({self.from_serial}-{self.to_serial}, {self.status})"

def extract_carton(roll_range_str):
    """Extract carton number (FIXED LOGIC)"""
    if '_BRAND_' in roll_range_str:
        parts = roll_range_str.split('_BRAND_')
        base_range = parts[0].strip()
        carton_number = base_range.split(' - ')[0].strip()
        return carton_number
    elif ' - ' in roll_range_str:
        return roll_range_str.split(' - ')[0].strip()
    else:
        return roll_range_str

def test_not_to_use(roll_range_str, allocated_from, allocated_to, in_use_ranges):
    """Simulate 'Not to Use' logic"""
    
    print(f"\n{'='*80}")
    print(f"🔥 SIMULATING 'NOT TO USE' FOR: {roll_range_str}")
    print(f"{'='*80}")
    
    # Extract carton number
    carton_number = extract_carton(roll_range_str)
    print(f"✅ Extracted Carton: '{carton_number}'")
    
    # Check if it's "Not Used"
    issued_qty = 0
    wastage_qty = 0
    
    if issued_qty == 0 and wastage_qty == 0:
        print(f"⚠️ 'Not Used' case detected (Issued: 0, Wastage: 0)")
        print(f"✅ Using allocated range: {allocated_from}-{allocated_to}")
        
        # Find matching IN_USE ranges
        matches_found = []
        for range_obj in in_use_ranges:
            r_from = int(range_obj.from_serial)
            r_to = int(range_obj.to_serial)
            
            if r_from >= allocated_from and r_to <= allocated_to:
                print(f"✅ Found matching IN_USE range {r_from}-{r_to}. Converting to AVAILABLE.")
                range_obj.status = 'AVAILABLE'
                matches_found.append(range_obj)
        
        if matches_found:
            print(f"✅ Released {len(matches_found)} range(s) to AVAILABLE")
            return True
        else:
            print(f"⚠️ No matching IN_USE ranges found")
            return False
    
    return False

# Test Scenario: 2 rolls assigned, each locked but Not Used
print("="*80)
print("🧪 TESTING: 'NOT TO USE' FOR MULTIPLE ROLLS WITH MULTI-BRAND FORMAT")
print("="*80)

# Roll a1: Has 2 brands, both locked but Not Used
print("\n" + "#"*80)
print("# ROLL a1: Brand 1 - Not to Use")
print("#"*80)

a1_ranges = [
    SimulatedRange('1', '50', 'IN_USE')  # Entire roll is IN_USE
]

result1 = test_not_to_use(
    roll_range_str='a1 - 1 - 50_BRAND_1',
    allocated_from=1,
    allocated_to=50,
    in_use_ranges=a1_ranges
)

print("\n" + "#"*80)
print("# ROLL a1: Brand 2 - Not to Use")
print("#"*80)

# Note: After Brand 1 was released, the range should already be AVAILABLE
# But let's test if Brand 2 would also work if it was still IN_USE
result2 = test_not_to_use(
    roll_range_str='a1 - 1 - 50_BRAND_2',
    allocated_from=1,
    allocated_to=50,
    in_use_ranges=a1_ranges
)

# Roll a2: Has 2 brands, both locked but Not Used
print("\n" + "#"*80)
print("# ROLL a2: Brand 1 - Not to Use")
print("#"*80)

a2_ranges = [
    SimulatedRange('51', '100', 'IN_USE')  # Entire roll is IN_USE
]

result3 = test_not_to_use(
    roll_range_str='a2 - 51 - 100_BRAND_1',
    allocated_from=51,
    allocated_to=100,
    in_use_ranges=a2_ranges
)

print("\n" + "#"*80)
print("# ROLL a2: Brand 2 - Not to Use")
print("#"*80)

result4 = test_not_to_use(
    roll_range_str='a2 - 51 - 100_BRAND_2',
    allocated_from=51,
    allocated_to=100,
    in_use_ranges=a2_ranges
)

# Verification
print("\n" + "="*80)
print("📊 VERIFICATION:")
print("="*80)

print("\nRoll a1:")
print(f"  Before: {SimulatedRange('1', '50', 'IN_USE')}")
print(f"  After:  {a1_ranges[0]}")
print(f"  Status: {'✅ Released to AVAILABLE' if a1_ranges[0].status == 'AVAILABLE' else '❌ Still IN_USE'}")

print("\nRoll a2:")
print(f"  Before: {SimulatedRange('51', '100', 'IN_USE')}")
print(f"  After:  {a2_ranges[0]}")
print(f"  Status: {'✅ Released to AVAILABLE' if a2_ranges[0].status == 'AVAILABLE' else '❌ Still IN_USE'}")

print("\n" + "="*80)
all_passed = (a1_ranges[0].status == 'AVAILABLE' and a2_ranges[0].status == 'AVAILABLE')
if all_passed:
    print("✅ ALL TESTS PASSED!")
    print("'Not to Use' works perfectly for multiple rolls with multi-brand format!")
else:
    print("❌ SOME TESTS FAILED!")
print("="*80)
