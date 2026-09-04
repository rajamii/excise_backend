from django.db import models

from utils.file_validation import secure_upload_filename


def upload_head_image_path(instance, filename):
    return secure_upload_filename(filename, 'about_us/heads_of_organisations')


'''
    Model: HeadOfOrganisation
    Stores About Us head of organisation profile details
'''

class HeadOfOrganisation(models.Model):
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    image = models.ImageField(upload_to=upload_head_image_path, max_length=500)

    def __str__(self):
        return f"{self.name} - {self.title}"


'''
    Model: ExciseSecretary
    Stores Excise Secretaries / Principal Secretaries contact details
'''

class ExciseSecretary(models.Model):
    name = models.CharField(max_length=255)
    designation = models.CharField(max_length=255)
    email = models.EmailField()
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.designation}"


class AboutUs(models.Model):
    title = models.CharField(max_length=255, default="Department")
    page_key = models.CharField(max_length=100, default="department", db_index=True)
    content = models.TextField()
    header_color = models.CharField(max_length=50, default="#1C2B78", blank=True)
    header_text_color = models.CharField(max_length=50, default="#ffffff", blank=True)
    card_bg_color = models.CharField(max_length=50, default="#ffffff", blank=True)
    accent_color = models.CharField(max_length=50, default="#1C2B78", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'masters_aboutus'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.page_key})"


'''
    Model: Department
    Stores Department / About Us content and styling dynamically
'''
class Department(models.Model):
    title = models.CharField(max_length=255, default="Department")
    content = models.TextField()
    header_color = models.CharField(max_length=50, default="#1C2B78", blank=True)
    header_text_color = models.CharField(max_length=50, default="#ffffff", blank=True)
    card_bg_color = models.CharField(max_length=50, default="#ffffff", blank=True)
    accent_color = models.CharField(max_length=50, default="#1C2B78", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Department'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


'''
    Model: ProductsServices
    Stores Products & Services content and styling dynamically
'''
class ProductsServices(models.Model):
    title = models.CharField(max_length=255, default="Products & Services")
    content = models.TextField()
    header_color = models.CharField(max_length=50, default="#1C2B78", blank=True)
    header_text_color = models.CharField(max_length=50, default="#ffffff", blank=True)
    card_bg_color = models.CharField(max_length=50, default="#ffffff", blank=True)
    accent_color = models.CharField(max_length=50, default="#1C2B78", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Products_Services'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


'''
    Model: RefundCancellationPolicy
    Stores Refund / Cancellation Policy content and styling dynamically
'''
class RefundCancellationPolicy(models.Model):
    title = models.CharField(max_length=255, default="Refund / Cancellation Policy")
    content = models.TextField()
    header_color = models.CharField(max_length=50, default="#1C2B78", blank=True)
    header_text_color = models.CharField(max_length=50, default="#ffffff", blank=True)
    card_bg_color = models.CharField(max_length=50, default="#ffffff", blank=True)
    accent_color = models.CharField(max_length=50, default="#1C2B78", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Refund_Cancellation_Policy'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


