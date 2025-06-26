from django.db import models
from .validators import validate_name , validate_Numbers

#License Category
class LicenseCategory(models.Model):
    license_category= models.CharField(max_length=200,default=None,null=False)

#License Type  
class LicenseType(models.Model):
    license_type= models.CharField(max_length=200,default=None,null=False)    

#State 
class State(models.Model):
    state = models.CharField(default='Sikkim')
    state_name_ll = models.CharField(max_length=30,validators=[validate_name])
    state_code = models.IntegerField(unique=True,default=11,)
    is_active = models.BooleanField(default=True)

    def _str_(self):
        return self.state

#District
class District(models.Model):
    district = models.CharField(max_length=30,validators=[validate_name])
    district_name_ll = models.CharField(max_length=30,validators=[validate_name],null=True)
    # if Null !=True:every Subdivision would require a valid District to be assigned. 
    district_code = models.IntegerField(unique=True,default=117)
    is_active = models.BooleanField(default=True)
    state_code = models.ForeignKey(
        State, 
        to_field='state_code', 
        on_delete=models.CASCADE,
        related_name='districts',
        null=True,
        db_column='state_code' 
    )

    def _str_(self):
        return self.district

#Subdivision
class Subdivision(models.Model):
    subdivision = models.CharField(max_length=30,validators=[validate_name],null=True)
    subdivision_name_ll = models.CharField(max_length=30,validators=[validate_name],null=True)
    subdivision_code = models.IntegerField(unique=True,default=1001)
    is_active = models.BooleanField(default=True)
    district_code = models.ForeignKey(
        District, 
        to_field='district_code', 
        on_delete=models.CASCADE, 
        related_name='subdivisions', 
        null=True,
        db_column='district_code', 
        )

    def _str_(self):
        return self.subdivision

#PoliceStation
class PoliceStation(models.Model):
    police_station = models.CharField(max_length=30,validators=[validate_name],null=True)
    police_station_code= models.IntegerField(unique=True,default=11999)
    is_active= models.BooleanField(default=True)
    subdivision_code=models.ForeignKey(
        Subdivision, 
        to_field='subdivision_code',
        on_delete=models.CASCADE, 
        related_name='policestation', 
        null=True,
        db_column='subdivision_code'
    )
    def _str_(self):
        return self.police_station
           
    
