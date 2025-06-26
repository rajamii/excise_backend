from django.db import models
from .validators import validate_name
  

#State 
class State(models.Model):
    state = models.CharField(max_length=30,validators=[validate_name])
    state_code= models.IntegerField(unique=True)
    is_active= models.BooleanField(default=True)

    def __str__(self):
        return self.state

#District
class District(models.Model):
    district=models.CharField(max_length=30,validators=[validate_name])
    # if Null !=True:every Subdivision would require a valid District to be assigned. 
    district_code= models.IntegerField(unique=True)
    is_active= models.BooleanField(default=True)
    state_code= models.ForeignKey(State, to_field='StateCode', on_delete=models.CASCADE,related_name='districts')

    def __str__(self):
        return self.district

#Subdivision
class Subdivision(models.Model):
    subdivision=models.CharField(max_length=30,validators=[validate_name])
    subdivision_code= models.IntegerField(unique=True)
    is_active= models.BooleanField(default=True)
    district_code = models.ForeignKey(District, to_field='DistrictCode', on_delete=models.CASCADE, related_name='subdivisions')

    def __str__(self):
        return self.subdivision

#PoliceStation
class PoliceStation(models.Model):
    police_station=models.CharField(max_length=30,validators=[validate_name])
    police_station_code= models.IntegerField(unique=True)
    is_active= models.BooleanField(default=True)
    subdivision_code=models.ForeignKey(Subdivision, to_field='SubDivisionCode', on_delete=models.CASCADE, related_name='policestations')
    def __str__(self):
        return self.police_station
           

#License Category
class LicenseCategory(models.Model):
    license_category= models.CharField(max_length=200,default=None,null=False)
    def __str__(self):
        return self.license_category

#License Type  
class LicenseType(models.Model):
    license_type= models.CharField(max_length=200,default=None,null=False)  
    def __str__(self):
        return self.license_type
    
