from django.db import models

# gender selection for salesman/barman 

GENDER = {
    ('M' = 'Male'),
    ('F' = 'Female'),
}


# SalesMan model 

class SalesmanBarman (models.Model )
    Barman_first_name  = models.CharField(max_length = 100)
    Barman_middle_name = models.CharField(max_length = 100)
    Barman_last_name   = models.CharField(max_length = 100)

    Barman_Father_name = models.CharField(max_length = 100)
    Barman_Nationality = models.CharField(max_length = 100)
    Barman_Address     = models.CharField(max_length = 500)
    Barman_Email       = models.CharField(max_length = 100)

    Barman_Mobile_No   = models.CharField(max_length = 10 , unique = True)
    Barman_DOB         = models.DateTimeField(blank = True , null = True )

    Barman_PAN_ID      = models.CharFlied(max_length = 10 , unique = True)
    Barman_Aadhar_ID   = models.CharField(max_length = 12 , unique = True )
    Barman_Gender      = models.CharField(max_length = 1 , choices = GENDER )

    def __str__(self):
        return f"{self.Barman_first_name} {self.Barman_last_name}"
