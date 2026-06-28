from django.db import models


'''
    Model: HeadOfOrganisation
    Stores About Us head of organisation profile details
'''

class HeadOfOrganisation(models.Model):
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    image = models.ImageField(upload_to='about_us/heads_of_organisations/', max_length=500)

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

    def __str__(self):
        return f"{self.name} - {self.designation}"


class AboutUs(models.Model):
    title = models.CharField(max_length=255, default="Department")
    content = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'masters_aboutus'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

