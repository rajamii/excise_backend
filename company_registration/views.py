from rest_framework.views import APIView
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework import response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .serializers import CompanySerializer
from .models import CompanyModel
from rest_framework.parsers import MultiPartParser, FormParser

from roles.models import Role
from roles.views import is_role_capable_of

# View to handle company creation
class CompanyCreateView(APIView):
    # Enable support for file uploads (PDFs, documents, etc.)
    parser_classes = (MultiPartParser, FormParser)

    # Handle POST request to create a new company record
    def post(self, request, *args, **kwargs):

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='company_registration'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        serializer = CompanySerializer(data=request.data)  # Deserialize incoming data
        if serializer.is_valid():
            serializer.save()  # Save the new company to the database
            return Response(serializer.data, status=status.HTTP_201_CREATED)  # Return created data
        print("Validation Errors:", serializer.errors)  # Debug print for server logs
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)  # Return validation errors

# View to handle listing or retrieving companies
class CompanyListView(APIView):

    # Handle GET requests to either list all companies or get one by ID
    def get(self, request, pk=None):

        if is_role_capable_of(
            request=request,
            operation=Role.READ,
            model='company_registration'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        if pk is not None:
            # Retrieve a single company by primary key (ID)
            instance = get_object_or_404(CompanyModel, pk=pk)
            serializer = CompanySerializer(instance)
            return Response(serializer.data)

        # If no pk provided, list all companies
        queryset = CompanyModel.objects.all()
        serializer = CompanySerializer(queryset, many=True)
        return Response(serializer.data)
