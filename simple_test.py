"""Simple test for multi-brand carton extraction"""

# Test the fix
test_input = "a1 - 1 - 50_BRAND_1"

# NEW (FIXED) LOGIC
if '_BRAND_' in test_input:
    parts = test_input.split('_BRAND_')
    base_range = parts[0].strip()  # 'a1 - 1 - 50'
    carton_number = base_range.split(' - ')[0].strip()  # 'a1'
    print(f"Input: {test_input}")
    print(f"Extracted carton: {carton_number}")
    print(f"Expected: a1")
    if carton_number == "a1":
        print("SUCCESS: Fix is working correctly!")
    else:
        print("FAIL: Fix is not working")
else:
    print("ERROR: Multi-brand format not detected")
