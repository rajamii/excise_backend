from django.db import models

# gender selection for salesman/barman 

GENDER = {
    ('M' , 'Male'),
    ('F' , 'Female'),
}

# SalesMan model 

class SalesmanBarman (models.Model ):
    first_name  = models.CharField(max_length = 100)
    middle_name = models.CharField(max_length = 100)
    last_name   = models.CharField(max_length = 100)

    Father_name = models.CharField(max_length = 100)
    Nationality = models.CharField(max_length = 100)
    Address     = models.CharField(max_length = 500)
    Email       = models.CharField(max_length = 100)

    Mobile_No   = models.CharField(max_length = 10 , unique = True)
    DOB         = models.DateTimeField(blank = True , null = True )

    PAN_ID      = models.CharField(max_length = 10 , unique = True)
    Aadhar_ID   = models.CharField(max_length = 12 , unique = True )
    Gender      = models.CharField(max_length = 1 , choices = GENDER )

    def __str__(self):
        return f"{self.Barman_first_name} {self.Barman_last_name}"
