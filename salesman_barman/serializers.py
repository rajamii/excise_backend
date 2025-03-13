from .models import SalesmanBarman
from rest_framework import serializers

class Salesman_BarManSerializer (serializers.ModelSerializer): 
    class Meta:
        model = SalesmanBarman
        fields = '__all__'
        
