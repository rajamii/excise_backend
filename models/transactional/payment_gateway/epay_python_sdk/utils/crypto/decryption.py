"""
Decryption utilities for payload decryption.
"""

import json
from typing import Dict, Any
from .aes import decrypt


def decrypt_payload(h_val: str, payload: Dict[str, Any], responseType: str) -> Dict[str, Any]:
    """
    Decrypt a payload using AES decryption.
    
    Args:
        h_val: The decryption key
        payload: The encrypted payload
        
    Returns:
        Decrypted response dictionary
    """
    
    response = payload.get('data', {})
    # print(f"\033[35m🌐🔓 Decryption response: {response}\033[0m")
    # print("-" * 10)

    decrypted_resp = {
        'status': response.get('status', 0),
        'data': []
    }

    # print(f"🔓 Decryption decrypted_resp: {decrypted_resp}")
    # print("-" * 10)
    
    try:
        if response.get('status') == 1:
            data_list = response.get('data', [])
            if response.get('count'):
                count = response.get('count')
            if response.get('total'):
                total =  response.get('total')
            # print(f"🔓 Decryption data_list: {data_list}")
            # print("-" * 10)
            if data_list:
                payload_details = data_list[0]
                # print(f"🔓 Decryption payload_details: {payload_details}")
                # print("-" * 10)
                if isinstance(payload_details, str):
                    decrypted_payload = decrypt(h_val, payload_details)
                    # print(f"🔓 Decryption decrypted_payload: {decrypted_payload}")
                    # print("-" * 10)
                    if responseType is "STRING":
                        if(response.get('count') and response.get('total')):
                            new_data = {
                                "data": json.loads(decrypted_payload),
                                "count": count,
                                "total": total
                            }
                            # print(f"🔓 Decryption new_data: {new_data}")
                            # print("-" * 10)
                            decrypted_resp['data'].append(json.dumps(new_data))
                        else:
                            decrypted_resp['data'].append(json.loads(json.dumps(decrypted_payload)))
                    else:
                        if(response.get('count') and response.get('total')):
                            new_data = {
                                "data": json.loads(decrypted_payload),
                                "count": count,
                                "total": total
                            }
                            # print(f"🔓 Decryption new_data: {new_data}")
                            # print("-" * 10)
                            decrypted_resp['data'].append(json.loads(json.dumps(new_data)))
                        else:
                            decrypted_resp['data'].append(json.loads(decrypted_payload))
                            # print(f"🔓 Decryption if decrypted_resp: {decrypted_resp}")
                            # print("-" * 10)
                else:
                    decrypted_payload = decrypt(h_val, payload_details.get('encryptedResponse'))
                    # print(f"🔓 Decryption else decrypted_payload: {payload_details.get('encryptedResponse')}")
                    # print("-" * 10)
                    if responseType is "STRING":
                        decrypted_resp['data'].append(json.loads(json.dumps(decrypted_payload)))
                    else:
                        decrypted_resp['data'].append(json.loads(decrypted_payload))
                    # print(f"🔓 Decryption else decrypted_resp: {decrypted_resp}")
                    # print("-" * 10)
            return decrypted_resp
        elif response.get('status') == 0:
            # print(f"🔓 Decryption response: {response}")
            # print("-" * 10)
            return response
        else:
            # print(f"🔓 Decryption decrypted_resp: {decrypted_resp}")
            # print("-" * 10)
            return decrypted_resp
    except Exception as err:
        raise Exception(f"Decryption error: {str(err)}")