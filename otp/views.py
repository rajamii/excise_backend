from .helpers import send_otp_code
from .models import OTP

def check_phone_numbers(phone_number):
    if OTP.objects.filter(phone_number=phone_number).exists():
        return True
    return False

def send_otp(phone_number):
    user = OTP.objects.create(
        phone_number=phone_number,
        otp=send_otp_code(phone_number),
    )
    user.save()

def verify_otp(phone_number, otp):
    obj = OTP.objects.get(phone_number=phone_number)
    if obj.otp == otp:
        return True
    return False

def delete(phone_number):
    try:
        OTP.objects.get(phone_number=phone_number).delete()

    except Exception as e:
        raise ValueError(f"{e}")