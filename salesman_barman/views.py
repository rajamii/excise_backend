from rest_framework.views import APIView
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .serializers import SalesmanBarmanSerializer
from .models import SalesmanBarmanModel

class SalesmanCreateView(APIView):

    def post(self , request , *args , **kwargs):
        serializer = SalesmanBarmanSerializer(data=request)
        if serializer.is_valid():
            serializer.save()
            return Response({"success" : "salesman / barman created successfully"} , status=status.HTTP_201_CREATED )
        return Response(serializer.errors , status=status.HTTP_400_BAD_REQUEST)        


class SalesmanListView(APIView):

    def get(self , request , pk=None):
        if pk:
            return get_object_or_404(SalesmanBarmanModel , pk=pk)
        salesman = SalesmanBarmanModel.objects.all()
        serializer = SalesmanBarmanSerializer(salesman , many=True)
        return Response(serializer.data)

            
        
