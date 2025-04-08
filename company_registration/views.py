from rest_framework.views import APIView
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .serializers import CompanySerializer
from .models import CompanyModel
from rest_framework.parsers import MultiPartParser, FormParser

class CompanyCreateView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        serializer = CompanySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        print("Validation Errors:", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)     


class CompanyListView(APIView):

    def get(self, request, pk=None):
        if pk is not None:
            instance = get_object_or_404(CompanyModel, pk=pk)
            serializer = CompanySerializer(instance)
            return Response(serializer.data)
    
        queryset = CompanyModel.objects.all()
        serializer = CompanySerializer(queryset, many=True)
        return Response(serializer.data)

            
        
