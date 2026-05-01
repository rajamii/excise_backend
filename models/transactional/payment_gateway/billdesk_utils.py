import hmac
import hashlib
import json
import base64

def _base64url_encode(data: bytes) -> str:
    """
    Encodes data to Base64URL format without padding '=' as required by JWS standards.
    """
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

def generate_billdesk_jws(client_id: str, secret_key: str, payload_dict: dict) -> str:
    """
    Generates a JWS-HMAC token for BillDesk Create Order API.
    """
    # 1. Create the Header
    # The algorithm must be HS256 and clientid must be passed in the header[cite: 1]
    
    header_dict = {
        "alg": "HS256",
        "clientid": client_id
    }
    
    # 2. Encode Header and Payload
    # Ensure JSON is compact without spaces to match signature expectations
    
    header_json = json.dumps(header_dict, separators=(',', ':')).encode('utf-8')
    payload_json = json.dumps(payload_dict, separators=(',', ':')).encode('utf-8')
    
    encoded_header = _base64url_encode(header_json)
    encoded_payload = _base64url_encode(payload_json)
    
    # 3. Create the Signature String
    # The signature string is the encoded header and payload joined by a period[cite: 1]
    
    signature_string = f"{encoded_header}.{encoded_payload}"
    
    # 4. Generate the HMAC-SHA256 Signature using the secret_key[cite: 1]
    
    signature_bytes = hmac.new(
        secret_key.encode('utf-8'),
        signature_string.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    encoded_signature = _base64url_encode(signature_bytes)
    
    # 5. Return the final JWS token[cite: 1]
    
    final_jws = f"{signature_string}.{encoded_signature}"
    return final_jws

def verify_billdesk_jws(jws_token: str, secret_key: str) -> bool:
    """
    Verifies the JWS-HMAC signature of an incoming Billdesk response.
    """
    parts = jws_token.split('.')
    if len(parts) != 3:
        return False

    encoded_header, encoded_payload, provided_signature = parts
    
    # The signature string is the encoded header and payload joined by a period
    signature_string = f"{encoded_header}.{encoded_payload}"

    # Generate the expected HMAC-SHA256 Signature using the secret_key
    expected_signature_bytes = hmac.new(
        secret_key.encode('utf-8'),
        signature_string.encode('utf-8'),
        hashlib.sha256
    ).digest()

    # Base64URL encode without padding
    expected_signature = base64.urlsafe_b64encode(expected_signature_bytes).decode('utf-8').rstrip('=')

    # Use hmac.compare_digest to prevent timing attacks
    return hmac.compare_digest(expected_signature, provided_signature)