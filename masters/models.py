from django.db import models
from .validators import validate_name
  

#State 
class State(models.Model):
    State = models.CharField(max_length=30,validators=[validate_name])
    StateCode= models.IntegerField(unique=True)
    IsActive= models.BooleanField(default=True)

    def __str__(self):
        return self.State

#District
class District(models.Model):
    District=models.CharField(max_length=30,validators=[validate_name])
    # if Null !=True:every Subdivision would require a valid District to be assigned. 
    DistrictCode= models.IntegerField(unique=True)
    IsActive= models.BooleanField(default=True)
    StateCode= models.ForeignKey(State, to_field='StateCode', on_delete=models.CASCADE,related_name='districts')

    def __str__(self):
        return self.District

#Subdivision
class Subdivision(models.Model):
    SubDivisionName=models.CharField(max_length=30,validators=[validate_name])
    SubDivisionCode= models.IntegerField(unique=True)
    IsActive= models.BooleanField(default=True)
    DistrictCode = models.ForeignKey(District, to_field='DistrictCode', on_delete=models.CASCADE, related_name='subdivisions')

    def __str__(self):
        return self.SubDivisionName

#PoliceStation
class PoliceStation(models.Model):
    PoliceStationName=models.CharField(max_length=30,validators=[validate_name])
    PoliceStationCode= models.IntegerField(unique=True)
    IsActive= models.BooleanField(default=True)
    SubDivisionCode=models.ForeignKey(Subdivision, to_field='SubDivisionCode', on_delete=models.CASCADE, related_name='policestations')
    def __str__(self):
        return self.PoliceStationName
           

#License Category
class LicenseCategory(models.Model):
    licenseCategoryDescription= models.CharField(max_length=200,default=None,null=False)
    def __str__(self):
        return self.licenseCategoryDescription

#License Type  
class LicenseType(models.Model):
    licenseType= models.CharField(max_length=200,default=None,null=False)  
    def __str__(self):
        return self.licenseType
    
