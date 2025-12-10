import random
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from auth.user.models import OTP

def get_new_otp(phone_number):

    fifteen_minutes_ago = timezone.now() - timedelta(minutes=15)
    recent_otps_count = OTP.objects.filter(
        phone_number=phone_number,
        created_at__gte=fifteen_minutes_ago
    ).count()

    if recent_otps_count >= 3:
        raise ValueError("Too many OTP requests. Please try again after 15 minutes.")
    
    OTP.objects.filter(
        phone_number=phone_number,
        created_at__lt=fifteen_minutes_ago,
        used=False
    ).delete()

    otp_value = str(random.randint(1000, 9999))
    otp_obj = OTP.objects.create(phone_number=phone_number, otp=otp_value)
    return otp_obj

@transaction.atomic
def verify_otp(otp_id, phone_number, otp_input):
    try:
        otp_obj = OTP.objects.get(id=otp_id, phone_number=phone_number, used=False)
        if otp_obj.is_expired():
            otp_obj.delete()
            return False, "OTP expired."
        if otp_obj.otp != str(otp_input):
            return False, "Incorrect OTP."
        
        otp_obj.used = True
        otp_obj.save()
        otp_obj.delete()
    
        return True, "OTP verified."
        
    except OTP.DoesNotExist:
        return False, "Invalid OTP or already used."
    


