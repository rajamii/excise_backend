import random

def send_otp_code(phone_number):
    try:
        otp = random.randint(100000, 999999)
        return otp
    
    except Exception as e:
        return None