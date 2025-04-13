
from rest_framework.views import APIView
from django.http import JsonResponse  # Not used directly in this code, but useful for custom responses
from rest_framework.response import Response  # Used to return API responses
from rest_framework import status  # For HTTP status codes
from django.shortcuts import get_object_or_404  # For safely retrieving objects or returning 404
from .serializers import SalesmanBarmanSerializer  # Importing the serializer for SalesmanBarman
from .models import SalesmanBarmanModel  # Importing the model being used
from rest_framework.parsers import MultiPartParser, FormParser  # To handle file uploads (e.g., images, documents)

# API view to create a new Salesman/Barman instance
class SalesmanCreateView(APIView):
    # Allow parsing of multipart and form-data (required for file uploads or complex form submissions)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        # Deserialize incoming request data
        serializer = SalesmanBarmanSerializer(data=request.data)
        
        # Validate the data
        if serializer.is_valid():
            serializer.save()  # Save the validated data to the database
            return Response(serializer.data, status=status.HTTP_201_CREATED)  # Return success response

        # If validation fails, print the errors to console (for debugging) and return 400 response
        print("Validation Errors:", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# API view to list Salesman/Barman instances or retrieve a specific one
class SalesmanListView(APIView):

    def get(self, request, pk=None):
        # If a primary key is provided in the request, return the specific instance
        if pk is not None:
            instance = get_object_or_404(SalesmanBarmanModel, pk=pk)  # Retrieve the object or return 404
            serializer = SalesmanBarmanSerializer(instance)  # Serialize the object
            return Response(serializer.data)  # Return the serialized data
        
        # If no primary key is provided, return the list of all instances
        queryset = SalesmanBarmanModel.objects.all()  # Get all objects
        serializer = SalesmanBarmanSerializer(queryset, many=True)  # Serialize the list of objects
        return Response(serializer.data)  # Return the serialized list
