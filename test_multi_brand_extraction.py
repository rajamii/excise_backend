"""
Test script to verify multi-brand carton number extraction logic
"""

def extract_carton_old(roll_range_str):
    """OLD (BROKEN) LOGIC"""
    if '_BRAND_' in roll_range_str:
        parts = roll_range_str.split('_BRAND_')
        carton_number = parts[0].strip()
        return carton_number
    elif ' - ' in roll_range_str:
        parts = roll_range_str.split(' - ')
        carton_number = parts[0].strip()
        return carton_number
    else:
        return roll_range_str

def extract_carton_new(roll_range_str):
    """NEW (FIXED) LOGIC"""
    if '_BRAND_' in roll_range_str:
        # Multi-brand format: 'a1 - 1 - 50_BRAND_1'
        # Extract the base part before '_BRAND_' and then get the first element (carton number)
        parts = roll_range_str.split('_BRAND_')
        base_range = parts[0].strip()  # 'a1 - 1 - 50'
        # Now extract just the carton number (first part before ' - ')
        carton_number = base_range.split(' - ')[0].strip()  # 'a1'
        return carton_number
    elif ' - ' in roll_range_str:
        parts = roll_range_str.split(' - ')
        carton_number = parts[0].strip()
        return carton_number
    else:
        return roll_range_str

# Test cases
test_cases = [
    # Multi-brand formats
    "a1 - 1 - 50_BRAND_1",
    "a1 - 1 - 50_BRAND_2",
    "a2 - 51 - 100_BRAND_1",
    "a2 - 51 - 100_BRAND_2",
    "a3 - 101 - 1000_BRAND_1",
    
    # Single-brand formats (should still work)
    "a1 - 1 - 50",
    "a2 - 51 - 100",
    "a3 - 101 - 1000",
    
    # Edge cases
    "a1",
    "a2-51-100",
]

print("="*80)
print("🧪 MULTI-BRAND CARTON EXTRACTION TEST")
print("="*80)
print()

all_passed = True

for i, test_input in enumerate(test_cases, 1):
    old_result = extract_carton_old(test_input)
    new_result = extract_carton_new(test_input)
    
    # Expected result
    if '_BRAND_' in test_input:
        expected = test_input.split('_BRAND_')[0].strip().split(' - ')[0].strip()
    elif ' - ' in test_input:
        expected = test_input.split(' - ')[0].strip()
    elif '-' in test_input:
        expected = test_input.split('-')[0].strip()
    else:
        expected = test_input
    
    # Check if new logic is correct
    is_correct = (new_result == expected)
    is_fixed = (old_result != new_result and is_correct) or (old_result == new_result and is_correct)
    
    status = "✅ PASS" if is_correct else "❌ FAIL"
    
    print(f"Test {i}: {test_input}")
    print(f"  Expected:  '{expected}'")
    print(f"  OLD Logic: '{old_result}' {'❌ WRONG' if old_result != expected else '✓'}")
    print(f"  NEW Logic: '{new_result}' {'✅ CORRECT' if new_result == expected else '❌ WRONG'}")
    print(f"  Status:    {status}")
    print()
    
    if not is_correct:
        all_passed = False

print("="*80)
if all_passed:
    print("✅ ALL TESTS PASSED! The fix is working correctly.")
else:
    print("❌ SOME TESTS FAILED! There are still issues to fix.")
print("="*80)
print()

# Specific test for the reported bug
print("="*80)
print("🔍 SPECIFIC BUG TEST (from logs)")
print("="*80)
print()

bug_test = "a1 - 1 - 50_BRAND_1"
print(f"Input: '{bug_test}'")
print()

old = extract_carton_old(bug_test)
new = extract_carton_new(bug_test)

print(f"OLD Logic Result: '{old}'")
print(f"  → Would try to find carton '{old}' in database ❌ WRONG")
print()

print(f"NEW Logic Result: '{new}'")
print(f"  → Will correctly find carton '{new}' in database ✅ CORRECT")
print()

if new == "a1":
    print("✅ BUG FIXED! Carton extraction now works correctly for multi-brand entries.")
else:
    print(f"❌ BUG NOT FIXED! Expected 'a1' but got '{new}'")
print("="*80)
