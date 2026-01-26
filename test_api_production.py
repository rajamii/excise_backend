import requests

# Test the production-history endpoint
brand_id = 312  # From the error log
url = f"http://127.0.0.1:8000/api/transactional/supply_chain/brand_warehouse/brand-warehouse/{brand_id}/production-history/"
params = {
    'limit': 10,
    'days': 30
}

print(f"Testing URL: {url}")
print(f"Parameters: {params}")

try:
    response = requests.get(url, params=params)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
    print(f"Response text: {response.text if 'response' in locals() else 'No response'}")
