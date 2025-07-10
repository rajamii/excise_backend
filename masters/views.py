from rest_framework import generics, response, status
from rest_framework.exceptions import NotFound
from masters import models as masters_models
from masters import serializers as ser
from roles.models import Role
from roles.views import is_role_capable_of

# LicenseCategoryAPI: For listing, creating, updating, and deleting license categories
class LicenseCategoryAPI(generics.ListCreateAPIView,
                         generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_models.LicenseCategory.objects.all()
    serializer_class = ser.LicenseCategorySerializer
    lookup_field = 'id'

    def post(self, request, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        serializer = ser.LicenseCategorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        if is_role_capable_of(request=request, operation=Role.READ, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        if id:
            license_category = masters_models.LicenseCategory.objects.get(id=id)
            serializer = ser.LicenseCategorySerializer(license_category)
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        license_categories = masters_models.LicenseCategory.objects.all()
        serializer = ser.LicenseCategorySerializer(license_categories, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        license_category = masters_models.LicenseCategory.objects.get(id=id)
        serializer = ser.LicenseCategorySerializer(license_category, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            license_category = masters_models.LicenseCategory.objects.get(id=id)
            license_category.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_models.LicenseCategory.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# LicenseTypeAPI: For listing, creating, updating, and deleting license types
class LicenseTypeAPI(generics.ListCreateAPIView,
                     generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_models.LicenseType.objects.all()
    serializer_class = ser.LicenseTypeSerializer
    lookup_field = 'id'

    def post(self, request, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        serializer = ser.LicenseTypeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        if is_role_capable_of(request=request, operation=Role.READ, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        if id:
            try:
                license_type = masters_models.LicenseType.objects.get(id=id)
                serializer = self.serializer_class(license_type)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_models.LicenseType.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)
        license_types = masters_models.LicenseType.objects.all()
        serializer = self.serializer_class(license_types, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            license_type = masters_models.LicenseType.objects.get(id=id)
            serializer = self.serializer_class(license_type, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_models.LicenseType.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            license_type = masters_models.LicenseType.objects.get(id=id)
            license_type.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_models.LicenseType.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# SubDivisionAPI: For creating, retrieving, updating, and deleting subdivisions
class SubdivisionApi(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_models.Subdivision.objects.all()  # Fetch all subdivisions
    # Define the serializer for Subdivision
    serializer_class = ser.SubdivisionSerializer
    lookup_field = 'id'  # Define the field for lookup (by id)

    def post(self, request, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        serializer = ser.SubdivisionSerializer(data=request.data)  # Fixed typo
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, dc=None, format=None):
        if is_role_capable_of(request=request, operation=Role.READ, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        if id:
            try:
                subdivision = masters_models.Subdivision.objects.get(id=id)
                serializer = self.serializer_class(subdivision)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_models.Subdivision.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)

        if dc is not None:  # Fetch by district code
            subdivisions = masters_models.Subdivision.objects.filter(
                district_code=dc)
            if not subdivisions.exists():
                raise NotFound(detail="No subdivisions found for this district code", code=status.HTTP_404_NOT_FOUND)
            serializer = self.serializer_class(subdivisions, many=True)
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        subdivisions = masters_models.Subdivision.objects.all()
        serializer = self.serializer_class(subdivisions, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            subdivision = masters_models.Subdivision.objects.get(id=id)
            serializer = self.serializer_class(subdivision, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_models.Subdivision.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            subdivision = masters_models.Subdivision.objects.get(id=id)
            subdivision.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_models.Subdivision.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# DistrictAPI: For listing, creating, updating, and deleting districts
class DistrictAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_models.District.objects.all()
    serializer_class = ser.DistrictSerializer
    lookup_field = 'id'

    def post(self, request, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        if is_role_capable_of(request=request, operation=Role.READ, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        if id:
            try:
                district = masters_models.District.objects.get(id=id)
                serializer = self.serializer_class(district)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_models.District.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)
        districts = masters_models.District.objects.all()
        serializer = self.serializer_class(districts, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            district = masters_models.District.objects.get(id=id)
            serializer = self.serializer_class(district, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_models.District.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            district = masters_models.District.objects.get(id=id)
            district.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_models.District.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# PoliceStationAPI: For listing, creating, updating, and deleting police stations
class PoliceStationAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_models.PoliceStation.objects.all()
    serializer_class = ser.PoliceStationSerializer
    lookup_field = 'id'

    def post(self, request, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        serializer = ser.PoliceStationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        if is_role_capable_of(request=request, operation=Role.READ, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        if id:
            policestation = masters_models.PoliceStation.objects.get(id=id)
            serializer = ser.PoliceStationSerializer(policestation)
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        police_stations = masters_models.PoliceStation.objects.all()
        serializer = ser.PoliceStationSerializer(police_stations, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        policestation = masters_models.PoliceStation.objects.get(id=id)
        serializer = ser.PoliceStationSerializer(policestation, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            policestation = masters_models.PoliceStation.objects.get(id=id)
            policestation.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_models.PoliceStation.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# LicenseSubcategoryAPI: For listing, creating, updating, and deleting license subcategories
class LicenseSubcategoryAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_models.LicenseSubcategory.objects.all()
    serializer_class = ser.LicenseSubcategorySerializer
    lookup_field = 'id'

    def post(self, request, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        serializer = ser.LicenseSubcategorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        if is_role_capable_of(request=request, operation=Role.READ, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        if id:
            try:
                subcategory = masters_models.LicenseSubcategory.objects.get(id=id)
                serializer = self.serializer_class(subcategory)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_models.LicenseSubcategory.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)
        subcategories = masters_models.LicenseSubcategory.objects.all()
        serializer = self.serializer_class(subcategories, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            subcategory = masters_models.LicenseSubcategory.objects.get(id=id)
            serializer = self.serializer_class(subcategory, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_models.LicenseSubcategory.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            subcategory = masters_models.LicenseSubcategory.objects.get(id=id)
            subcategory.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_models.LicenseSubcategory.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# RoadAPI: For listing, creating, updating, and deleting roads
class RoadAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_models.Road.objects.all()
    serializer_class = ser.RoadSerializer
    lookup_field = 'id'

    def post(self, request, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        serializer = ser.RoadSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        if is_role_capable_of(request=request, operation=Role.READ, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        if id:
            try:
                road = masters_models.Road.objects.get(id=id)
                serializer = self.serializer_class(road)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_models.Road.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)
        roads = masters_models.Road.objects.all()
        serializer = self.serializer_class(roads, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            road = masters_models.Road.objects.get(id=id)
            serializer = self.serializer_class(road, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_models.Road.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            road = masters_models.Road.objects.get(id=id)
            road.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_models.Road.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

# LicenseTitleAPI: For listing, creating, updating, and deleting license titles
class LicenseTitleAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_models.LicenseTitle.objects.all()
    serializer_class = ser.LicenseTitleSerializer
    lookup_field = 'id'

    def post(self, request, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        serializer = ser.LicenseTitleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, id=None, format=None):
        if is_role_capable_of(request=request, operation=Role.READ, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        if id:
            try:
                license_title = masters_models.LicenseTitle.objects.get(id=id)
                serializer = self.serializer_class(license_title)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_models.LicenseTitle.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)
        license_titles = masters_models.LicenseTitle.objects.all()
        serializer = self.serializer_class(license_titles, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            license_title = masters_models.LicenseTitle.objects.get(id=id)
            serializer = self.serializer_class(license_title, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except masters_models.LicenseTitle.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        if is_role_capable_of(request=request, operation=Role.READ_WRITE, model='masters') is False:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            license_title = masters_models.LicenseTitle.objects.get(id=id)
            license_title.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_models.LicenseTitle.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)