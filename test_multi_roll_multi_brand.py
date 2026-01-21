"""
Test multi-brand functionality with MULTIPLE ROLLS assigned
Scenario: 2 rolls (a1, a2), each with 2 brands
"""

class SimulatedRoll:
    def __init__(self, carton_number, total_count):
        self.carton_number = carton_number
        self.total_count = total_count
        self.used = 0
        self.damaged = 0
    
    def update(self, issued_qty, wastage_qty):
        self.used += issued_qty
        self.damaged += wastage_qty
        return self
    
    @property
    def available(self):
        return self.total_count - self.used - self.damaged
    
    def __repr__(self):
        return f"Roll({self.carton_number}: total={self.total_count}, used={self.used}, available={self.available})"

def extract_carton(roll_range_str):
    """Extract carton number from roll range (FIXED LOGIC)"""
    if '_BRAND_' in roll_range_str:
        parts = roll_range_str.split('_BRAND_')
        base_range = parts[0].strip()
        carton_number = base_range.split(' - ')[0].strip()
        return carton_number
    elif ' - ' in roll_range_str:
        return roll_range_str.split(' - ')[0].strip()
    else:
        return roll_range_str

def simulate_multi_roll_multi_brand_save(entries, rolls):
    """Simulate saving multiple brands across multiple rolls"""
    print(f"\n{'='*80}")
    print(f"🔥 SIMULATING MULTI-ROLL MULTI-BRAND SAVE")
    print(f"{'='*80}\n")
    
    for i, entry in enumerate(entries, 1):
        roll_range = entry['roll_range']
        issued_qty = entry['issued_qty']
        wastage_qty = entry['wastage_qty']
        
        # Extract carton number
        carton_number = extract_carton(roll_range)
        
        print(f"Entry #{i}: {roll_range}")
        print(f"  → Extracted Carton: '{carton_number}'")
        print(f"  → Issued: {issued_qty}, Wastage: {wastage_qty}")
        
        # Find and update the corresponding roll
        roll = rolls.get(carton_number)
        if roll:
            before = f"used={roll.used}, available={roll.available}"
            roll.update(issued_qty, wastage_qty)
            after = f"used={roll.used}, available={roll.available}"
            print(f"  → Updated: {before} → {after} ✅")
        else:
            print(f"  → ERROR: Roll '{carton_number}' not found ❌")
        print()
    
    return rolls

# Initialize rolls
rolls = {
    'a1': SimulatedRoll('a1', total_count=50),
    'a2': SimulatedRoll('a2', total_count=50),
}

print("="*80)
print("🧪 TESTING: MULTIPLE ROLLS with MULTIPLE BRANDS")
print("="*80)
print("\n📊 Initial State:")
for carton, roll in rolls.items():
    print(f"  {roll}")

# Simulate saving 4 entries:
# - Roll a1: Brand 1, Brand 2
# - Roll a2: Brand 1, Brand 2
entries = [
    {'roll_range': 'a1 - 1 - 50_BRAND_1',    'issued_qty': 5, 'wastage_qty': 0},
    {'roll_range': 'a1 - 1 - 50_BRAND_2',    'issued_qty': 3, 'wastage_qty': 1},
    {'roll_range': 'a2 - 51 - 100_BRAND_1',  'issued_qty': 7, 'wastage_qty': 0},
    {'roll_range': 'a2 - 51 - 100_BRAND_2',  'issued_qty': 4, 'wastage_qty': 2},
]

rolls = simulate_multi_roll_multi_brand_save(entries, rolls)

# Verification
print("="*80)
print("📊 FINAL STATE:")
print("="*80)
for carton, roll in rolls.items():
    print(f"  {roll}")

print("\n" + "="*80)
print("✅ VERIFICATION:")
print("="*80)

# Expected results:
# a1: used = 5 + 3 = 8, damaged = 0 + 1 = 1, available = 50 - 8 - 1 = 41
# a2: used = 7 + 4 = 11, damaged = 0 + 2 = 2, available = 50 - 11 - 2 = 37

expected = {
    'a1': {'used': 8, 'damaged': 1, 'available': 41},
    'a2': {'used': 11, 'damaged': 2, 'available': 37},
}

all_correct = True
for carton, roll in rolls.items():
    exp = expected[carton]
    used_ok = roll.used == exp['used']
    damaged_ok = roll.damaged == exp['damaged']
    avail_ok = roll.available == exp['available']
    
    print(f"\nRoll {carton}:")
    print(f"  Used:      {roll.used} (expected: {exp['used']}) {'✅' if used_ok else '❌'}")
    print(f"  Damaged:   {roll.damaged} (expected: {exp['damaged']}) {'✅' if damaged_ok else '❌'}")
    print(f"  Available: {roll.available} (expected: {exp['available']}) {'✅' if avail_ok else '❌'}")
    
    if not (used_ok and damaged_ok and avail_ok):
        all_correct = False

print("\n" + "="*80)
if all_correct:
    print("✅ ALL TESTS PASSED!")
    print("Multi-brand works perfectly for MULTIPLE ROLLS!")
else:
    print("❌ SOME TESTS FAILED!")
print("="*80)
