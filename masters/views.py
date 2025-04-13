from rest_framework import generics, response, status
from masters import models as masters_model
from masters.serializers import (licensecategory_serializer, licensetype_serializer, placemaster_serializer)
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator

# LicenseCategoryAPI: For listing, creating, updating, and deleting license categories
class LicenseCategoryAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_model.LicenseCategory.objects.all()  # Fetch all license categories
    serializer_class = licensecategory_serializer.LicenseCategorySerializer  # Define the serializer for LicenseCategory
    lookup_field = 'id'  # Define the field for lookup (by id)

    def post(self, request, format=None):
        # POST request to create a new LicenseCategory
        serializer = licensecategory_serializer.LicenseCategorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        # GET request for retrieving one or more LicenseCategories
        if id:
            # Fetch a specific LicenseCategory by id
            license_category = masters_model.LicenseCategory.objects.get(id=id)
            serializer = licensecategory_serializer.LicenseCategorySerializer(license_category)
            return response.Response(serializer.data, status=status.HTTP_200_OK)

        # Fetch all LicenseCategories if no specific id provided
        license_categories = masters_model.LicenseCategory.objects.all()
        serializer = licensecategory_serializer.LicenseCategorySerializer(license_categories, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        # PUT request for updating a LicenseCategory
        license_category = masters_model.LicenseCategory.objects.get(id=id)
        serializer = licensecategory_serializer.LicenseCategorySerializer(license_category, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id, format=None):
        # DELETE request to remove a LicenseCategory
        try:
            license_category = masters_model.LicenseCategory.objects.get(id=id)
            license_category.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.LicenseCategory.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# LicenseTypeAPI: For listing, creating, updating, and deleting license types
class LicenseTypeAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_model.LicenseType.objects.all()  # Fetch all license types
    serializer_class = licensetype_serializer.LicenseTypeSerializer  # Define the serializer for LicenseType
    lookup_field = 'id'  # Define the field for lookup (by id)

    def post(self, request, format=None):
        # POST request to create a new LicenseType
        serializer = licensetype_serializer.LicenseTypeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        # GET request for retrieving one or more LicenseTypes
        if id:
            try:
                # Fetch a specific LicenseType by id
                license_type = masters_model.LicenseType.objects.get(id=id)
                serializer = self.serializer_class(license_type)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_model.LicenseType.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)

        # Fetch all LicenseTypes if no specific id provided
        license_types = masters_model.LicenseType.objects.all()
        serializer = self.serializer_class(license_types, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        # PUT request for updating a LicenseType
        try:
            license_type = masters_model.LicenseType.objects.get(id=id)
            serializer = self.serializer_class(license_type, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_model.LicenseType.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        # DELETE request to remove a LicenseType
        try:
            license_type = masters_model.LicenseType.objects.get(id=id)
            license_type.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.LicenseType.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# SubDivisonAPI: For creating, retrieving, updating, and deleting subdivisions
class SubDivisonApi(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_model.Subdivision.objects.all()  # Fetch all subdivisions
    serializer_class = placemaster_serializer.SubDivisonSerializer  # Define the serializer for Subdivision
    lookup_field = 'id'  # Define the field for lookup (by id)

    def post(self, request, format=None):
        # POST request to create a new Subdivision
        serializer = placemaster_serializer.SubDivisonSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, dc=None, format=None):
        # GET request for retrieving subdivisions based on various parameters
        if id:
            try:
                # Fetch a specific Subdivision by id
                subdivision = masters_model.Subdivision.objects.get(id=id)
                serializer = self.serializer_class(subdivision)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_model.Subdivision.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)

        if dc is not None:  # Fetch by district code
            subdivisions = masters_model.Subdivision.objects.filter(DistrictCode=dc)
            if not subdivisions.exists():
                raise NotFound(detail="No subdivisions found for this district code", code=status.HTTP_404_NOT_FOUND)
            serializer = self.serializer_class(subdivisions, many=True)
            return response.Response(serializer.data, status=status.HTTP_200_OK)

        # Fetch all subdivisions if no id or district code provided
        subdivisions = masters_model.Subdivision.objects.all()
        serializer = self.serializer_class(subdivisions, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        # PUT request for updating a Subdivision
        try:
            subdivision = masters_model.Subdivision.objects.get(id=id)
            serializer = self.serializer_class(subdivision, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_model.Subdivision.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        # DELETE request to remove a Subdivision
        try:
            subdivision = masters_model.Subdivision.objects.get(id=id)
            subdivision.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.Subdivision.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# DistrictAPI: For listing, creating, updating, and deleting districts
class DistrictAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_model.District.objects.all()  # Fetch all districts
    serializer_class = placemaster_serializer.DistrictSerializer  # Define the serializer for District
    lookup_field = 'id'  # Define the field for lookup (by id)

    def post(self, request, format=None):
        # POST request to create a new District
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        # GET request for retrieving one or more Districts
        if id:
            try:
                # Fetch a specific District by id
                district = masters_model.District.objects.get(id=id)
                serializer = self.serializer_class(district)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_model.District.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)

        # Fetch all Districts if no specific id provided
        districts = masters_model.District.objects.all()
        serializer = self.serializer_class(districts, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        # PUT request for updating a District
        try:
            district = masters_model.District.objects.get(id=id)
            serializer = self.serializer_class(district, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_model.District.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        # DELETE request to remove a District
        try:
            district = masters_model.District.objects.get(id=id)
            district.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.District.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# PoliceStationAPI: For listing, creating, updating, and deleting police stations
class PoliceStationAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_model.PoliceStation.objects.all()  # Fetch all police stations
    serializer_class = placemaster_serializer.PoliceStationSerializer  # Define the serializer for PoliceStation
    lookup_field = 'id'  # Define the field for lookup (by id)

    def post(self, request, format=None):
        # POST request to create a new PoliceStation
        serializer = placemaster_serializer.PoliceStationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        # GET request for retrieving one or more PoliceStations
        if id:
            # Fetch a specific PoliceStation by id
            policestation = masters_model.PoliceStation.objects.get(id=id)
            serializer = placemaster_serializer.PoliceStationSerializer(policestation)
            return response.Response(serializer.data, status=status.HTTP_200_OK)

        # Fetch all PoliceStations if no specific id provided
        police_stations = masters_model.PoliceStation.objects.all()
        serializer = placemaster_serializer.PoliceStationSerializer(police_stations, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        # PUT request for updating a PoliceStation
        policestation = masters_model.PoliceStation.objects.get(id=id)
        serializer = placemaster_serializer.PoliceStationSerializer(policestation, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id, format=None):
        # DELETE request to remove a PoliceStation
        try:
            policestation = masters_model.PoliceStation.objects.get(id=id)
            policestation.delete()
            return response.Response(status=status.HTTP_205_RESET_CONTENT)
        except masters_model.PoliceStation.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)
