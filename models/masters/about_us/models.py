from django.db import models
from utils.file_validation import secure_upload_filename


def upload_head_image_path(instance, filename):
    return f"about_us/heads_of_organisations/{secure_upload_filename(filename)}"


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

    def __str__(self):
        return f"{self.name} - {self.designation}"
