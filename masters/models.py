from django.db import models
from .validators import validate_name , validate_Numbers

#License Category
class LicenseCategory(models.Model):
    licenseCategoryDescription= models.CharField(max_length=200,default=None,null=False)

#License Type  
class LicenseType(models.Model):
    licenseType= models.CharField(max_length=200,default=None,null=False)    

#State 
class State(models.Model):
    State = models.CharField(default='Sikkim')
    StateNameLL=models.CharField(max_length=30,validators=[validate_name])
    StateCode= models.IntegerField(unique=True,default=11)
    IsActive= models.BooleanField(default=True)

    def _str_(self):
        return self.State

#District
class District(models.Model):
    District=models.CharField(max_length=30,validators=[validate_name])
    DistrictNameLL=models.CharField(max_length=30,validators=[validate_name],null=True)
    # if Null !=True:every Subdivision would require a valid District to be assigned. 
    DistrictCode= models.IntegerField(unique=True,default=117)
    IsActive= models.BooleanField(default=True)
    StateCode= models.ForeignKey(State, to_field='StateCode', on_delete=models.CASCADE,related_name='districts',null=True)

    def _str_(self):
        return self.District

#Subdivision
class Subdivision(models.Model):
    SubDivisionName=models.CharField(max_length=30,validators=[validate_name],null=True)
    SubDivisionNameLL=models.CharField(max_length=30,validators=[validate_name],null=True)
    SubDivisionCode= models.IntegerField(unique=True,default=1001)
    IsActive= models.BooleanField(default=True)
    DistrictCode = models.ForeignKey(District, to_field='DistrictCode', on_delete=models.CASCADE, related_name='subdivisions', null=True)

    def _str_(self):
        return self.SubDivisionName

#PoliceStation
class PoliceStation(models.Model):
    PoliceStationName=models.CharField(max_length=30,validators=[validate_name],null=True)
    PoliceStationCode= models.IntegerField(unique=True,default=11999)
    IsActive= models.BooleanField(default=True)
    SubDivisionCode=models.ForeignKey(Subdivision, to_field='SubDivisionCode', on_delete=models.CASCADE, related_name='policestation', null=True)
    def _str_(self):
        return self.PoliceStationName
           
    
