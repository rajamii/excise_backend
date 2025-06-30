from rest_framework import generics, response, status
from rest_framework.exceptions import NotFound
from masters import models as masters_model
from masters import serializers as ser
from roles.models import Role
from roles.views import is_role_capable_of

# LicenseCategoryAPI: For listing, creating,
# updating, and deleting license categories


class LicenseCategoryAPI(generics.ListCreateAPIView,
                         generics.RetrieveUpdateDestroyAPIView):
    # Fetch all license categories
    queryset = masters_model.LicenseCategory.objects.all()

    # Define the serializer for LicenseCategory
    serializer_class = ser.LicenseCategorySerializer

    lookup_field = 'id'  # Define the field for lookup (by id)

    # POST request to create a new LicenseCategory
    def post(self, request, format=None):

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        serializer = ser.LicenseCategorySerializer(
            data=request.data)

        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data,
                                     status=status.HTTP_201_CREATED)

        return response.Response(serializer.errors,
                                 status=status.HTTP_400_BAD_REQUEST)

    # GET request for retrieving one or more LicenseCategories
    def get(self, request, id=None, format=None):

        if is_role_capable_of(
            request=request,
            operation=Role.READ,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        if id:
            # Fetch a specific LicenseCategory by id
            license_category = masters_model.LicenseCategory.objects.get(id=id)
            serializer = ser.LicenseCategorySerializer(
                license_category)
            return response.Response(serializer.data,
                                     status=status.HTTP_200_OK)

        # Fetch all LicenseCategories if no specific id provided

        license_categories = masters_model.LicenseCategory.objects.all()
        serializer = ser.LicenseCategorySerializer(
            license_categories,
            many=True
        )

        return response.Response(serializer.data, status=status.HTTP_200_OK)

    # PUT request for updating a LicenseCategory
    def put(self, request, id, format=None):

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        license_category = masters_model.LicenseCategory.objects.get(id=id)
        serializer = ser.LicenseCategorySerializer(
            license_category, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data,
                                     status=status.HTTP_200_OK)

        return response.Response(serializer.errors,
                                 status=status.HTTP_400_BAD_REQUEST)

    # DELETE request to remove a LicenseCategory
    def delete(self, request, id, format=None):

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            license_category = masters_model.LicenseCategory.objects.get(id=id)
            license_category.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.LicenseCategory.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# LicenseTypeAPI: For listing, creating, updating, and deleting license types


class LicenseTypeAPI(generics.ListCreateAPIView,
                     generics.RetrieveUpdateDestroyAPIView):

    queryset = masters_model.LicenseType.objects.all()  # Fetch all license types
    # Define the serializer for LicenseType
    serializer_class = ser.LicenseTypeSerializer
    lookup_field = 'id'  # Define the field for lookup (by id)

    # POST request to create a new LicenseType
    def post(self, request, format=None):

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        serializer = ser.LicenseTypeSerializer(
            data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        # GET request for retrieving one or more LicenseTypes

        if is_role_capable_of(
            request=request,
            operation=Role.READ,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

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

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            license_type = masters_model.LicenseType.objects.get(id=id)
            serializer = self.serializer_class(
                license_type, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_model.LicenseType.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        # DELETE request to remove a LicenseType

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            license_type = masters_model.LicenseType.objects.get(id=id)
            license_type.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.LicenseType.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# SubDivisionAPI: For creating, retrieving, updating, and deleting subdivisions


class SubDivisionApi(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_model.Subdivision.objects.all()  # Fetch all subdivisions
    # Define the serializer for Subdivision
    serializer_class = ser.SubDivisonSerializer
    lookup_field = 'id'  # Define the field for lookup (by id)

    def post(self, request, format=None):
        # POST request to create a new Subdivision

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        serializer = ser.SubDivisionSerializer(
            data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, dc=None, format=None):
        # GET request for retrieving subdivisions based on various parameters

        if is_role_capable_of(
            request=request,
            operation=Role.READ,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        if id:
            try:
                # Fetch a specific Subdivision by id
                subdivision = masters_model.Subdivision.objects.get(id=id)
                serializer = self.serializer_class(subdivision)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_model.Subdivision.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)

        if dc is not None:  # Fetch by district code
            subdivisions = masters_model.Subdivision.objects.filter(
                DistrictCode=dc)
            if not subdivisions.exists():
                raise NotFound(
                    detail="No subdivisions found for this district code",
                    code=status.HTTP_404_NOT_FOUND)
            serializer = self.serializer_class(subdivisions, many=True)
            return response.Response(serializer.data, status=status.HTTP_200_OK)

        # Fetch all subdivisions if no id or district code provided
        subdivisions = masters_model.Subdivision.objects.all()
        serializer = self.serializer_class(subdivisions, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        # PUT request for updating a Subdivision

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            subdivision = masters_model.Subdivision.objects.get(id=id)
            serializer = self.serializer_class(
                subdivision, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_model.Subdivision.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        # DELETE request to remove a Subdivision

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            subdivision = masters_model.Subdivision.objects.get(id=id)
            subdivision.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.Subdivision.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# DistrictAPI: For listing, creating, updating, and deleting districts


class DistrictAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_model.District.objects.all()  # Fetch all districts
    # Define the serializer for District
    serializer_class = ser.DistrictSerializer
    lookup_field = 'id'  # Define the field for lookup (by id)

    def post(self, request, format=None):
        # POST request to create a new District

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        # GET request for retrieving one or more Districts

        if is_role_capable_of(
            request=request,
            operation=Role.READ,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

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

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            district = masters_model.District.objects.get(id=id)
            serializer = self.serializer_class(
                district, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_model.District.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        # DELETE request to remove a District

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            district = masters_model.District.objects.get(id=id)
            district.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.District.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# PoliceStationAPI: For listing, creating, updating, and deleting police stations


class PoliceStationAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_model.PoliceStation.objects.all()  # Fetch all police stations
    # Define the serializer for PoliceStation
    serializer_class = ser.PoliceStationSerializer
    lookup_field = 'id'  # Define the field for lookup (by id)

    def post(self, request, format=None):
        # POST request to create a new PoliceStation

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        serializer = ser.PoliceStationSerializer(
            data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        # GET request for retrieving one or more PoliceStations

        if is_role_capable_of(
            request=request,
            operation=Role.READ,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        if id:
            # Fetch a specific PoliceStation by id
            policestation = masters_model.PoliceStation.objects.get(id=id)
            serializer = ser.PoliceStationSerializer(
                policestation)
            return response.Response(serializer.data, status=status.HTTP_200_OK)

        # Fetch all PoliceStations if no specific id provided
        police_stations = masters_model.PoliceStation.objects.all()
        serializer = ser.PoliceStationSerializer(
            police_stations, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        # PUT request for updating a PoliceStation

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        policestation = masters_model.PoliceStation.objects.get(id=id)
        serializer = ser.PoliceStationSerializer(
            policestation, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id, format=None):
        # DELETE request to remove a PoliceStation

        if is_role_capable_of(
            request=request,
            operation=Role.READ_WRITE,
            model='masters'
        ) is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            policestation = masters_model.PoliceStation.objects.get(id=id)
            policestation.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.PoliceStation.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)
