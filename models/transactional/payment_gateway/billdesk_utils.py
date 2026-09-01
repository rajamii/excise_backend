import base64
import hashlib
import hmac
import json
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_ID = "SSarkHgNtCqz"
ENCRYPTION_KEY = "heSf1EoYL5f58vlhgTOWiEK9NqWhn0i2"
SIGNING_KEY = "YXIpsQAfhNSJgm22Gcb3YVSkNFIVN9xz"


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * ((-len(data)) % 4)
    return base64.urlsafe_b64decode(data + padding)


def generate_billdesk_nested_jose(
    client_id: str,
    payload_dict: dict,
    encryption_key: str = ENCRYPTION_KEY,
    signing_key: str = SIGNING_KEY,
    key_id: str = KEY_ID,
) -> str:
    """Step 1 & 2: Encrypt JSON to JWE (alg: dir, enc: A256GCM)[cite: 3]."""
    jwe_header = {
        "alg": "dir",
        "enc": "A256GCM",
        "kid": key_id,
        "clientid": client_id,
    }
    encoded_jwe_header = _base64url_encode(
        json.dumps(jwe_header, separators=(",", ":")).encode("utf-8")
    )

    # 12-byte IV for AES-GCM
    iv = os.urandom(12)
    aad = encoded_jwe_header.encode("ascii")
    plaintext = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")

    aesgcm = AESGCM(encryption_key.encode("utf-8"))
    # AESGCM in cryptography appends the 16-byte authentication tag at the end
    encrypted_data = aesgcm.encrypt(iv, plaintext, aad)
    ciphertext = encrypted_data[:-16]
    tag = encrypted_data[-16:]

    # JWE format: header.encrypted_key.iv.ciphertext.tag (encrypted_key is empty for "dir")
    jwe_token = f"{encoded_jwe_header}..{_base64url_encode(iv)}.{_base64url_encode(ciphertext)}.{_base64url_encode(tag)}"

    # Step 3: Sign the JWE token to create JWS (alg: HS256)[cite: 1, 3]
    jws_header = {
        "alg": "HS256",
        "kid": key_id,
        "clientid": client_id,
    }
    encoded_jws_header = _base64url_encode(
        json.dumps(jws_header, separators=(",", ":")).encode("utf-8")
    )
    encoded_jws_payload = _base64url_encode(jwe_token.encode("utf-8"))

    jws_signing_input = f"{encoded_jws_header}.{encoded_jws_payload}"
    signature = hmac.new(
        signing_key.encode("utf-8"),
        jws_signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    return f"{jws_signing_input}.{_base64url_encode(signature)}"


def decrypt_and_verify_billdesk_response(
    response_jwt: str,
    encryption_key: str = ENCRYPTION_KEY,
    signing_key: str = SIGNING_KEY,
) -> dict:
    """Verifies the outer JWS signature and decrypts the inner JWE payload[cite: 3]."""
    parts = response_jwt.strip().split(".")

    # Handle direct JWS (3 parts)
    if len(parts) == 3:
        header_b64, payload_b64, signature_b64 = parts

        # Verify JWS signature
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = _base64url_encode(
            hmac.new(
                signing_key.encode("utf-8"), signing_input, hashlib.sha256
            ).digest()
        )
        if not hmac.compare_digest(expected_sig, signature_b64):
            raise ValueError("Invalid JWS Signature from BillDesk")

        raw_payload = _base64url_decode(payload_b64).decode("utf-8")

        # If the inner payload is JWE (5 parts)[cite: 3]
        if raw_payload.count(".") == 4:
            return _decrypt_jwe_string(raw_payload, encryption_key)
        return json.loads(raw_payload)

    # Handle direct JWE (5 parts)
    if len(parts) == 5:
        return _decrypt_jwe_string(response_jwt, encryption_key)

    raise ValueError("Unrecognized response format from BillDesk")


def _decrypt_jwe_string(jwe_token: str, encryption_key: str) -> dict:
    header_b64, enc_key_b64, iv_b64, cipher_b64, tag_b64 = jwe_token.split(".")
    iv = _base64url_decode(iv_b64)
    ciphertext = _base64url_decode(cipher_b64)
    tag = _base64url_decode(tag_b64)
    aad = header_b64.encode("ascii")

    aesgcm = AESGCM(encryption_key.encode("utf-8"))
    decrypted_bytes = aesgcm.decrypt(iv, ciphertext + tag, aad)
    return json.loads(decrypted_bytes.decode("utf-8"))