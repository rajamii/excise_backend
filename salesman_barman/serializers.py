from .models import SalesmanBarman
from rest_framework import serializers

class SalesmanBarmanSerializer (serializers.ModelSerializer): 
    class Meta:
        model = SalesmanBarman
        fields = '__all__'
        
