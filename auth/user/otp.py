import random
from auth.user.models import OTP

def get_new_otp(phone_number):
    otp_value = str(random.randint(1000, 9999))
    otp_obj = OTP.objects.create(phone_number=phone_number, otp=otp_value)
    return otp_obj  # You can return otp_obj.id and otp_obj.otp for sending SMS

def verify_otp(otp_id, phone_number, otp_input):
    try:
        otp_obj = OTP.objects.get(id=otp_id, phone_number=phone_number, used=False)
        if otp_obj.is_expired():
            return False, "OTP expired."
        if otp_obj.otp != str(otp_input):
            return False, "Incorrect OTP."
        otp_obj.used = True
        otp_obj.save()
        return True, "OTP verified."
    except OTP.DoesNotExist:
        return False, "Invalid OTP or already used."
    


