"""
Encryption utilities for payload encryption.
"""

import json
from typing import Dict, Any
from .aes import encrypt


def encrypt_payload(h_val: str, payload: Dict[str, Any]) -> Dict[str, str]:
    """
    Encrypt a payload using AES encryption.
    
    Args:
        h_val: The encryption key
        payload: The payload to encrypt
        
    Returns:
        Dictionary containing the encrypted request
    """

    # print(f"\033[96m🌐🔐 Encryption json.dumps(payload): {json.dumps(payload)}\033[0m")
    # print("-" * 10)
    encrypted_payload = encrypt(h_val, json.dumps(payload))
    return {
        "encryptedRequest": encrypted_payload
    }