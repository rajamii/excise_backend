from django.db import models

class OTP(models.Model):
    phone_number = models.CharField(max_length=10, primary_key=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.phone_number} - {self.otp}"
