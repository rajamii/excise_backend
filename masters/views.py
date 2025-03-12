from rest_framework import generics, response, status
from masters import models as masters_model
from masters.serializers import (licensecategory_serializer, licensetype_serializer, placemaster_serializer)

# LicenseCategoryList for listing and creating
class LicenseCategoryList(generics.ListCreateAPIView):
    queryset = masters_model.LicenseCategory.objects.all().order_by('-id')
    serializer_class = licensecategory_serializer.LicenseCategorySerializer

# LicenseTypeList for listing and creating
class LicenseTypeList(generics.ListCreateAPIView):
    queryset = masters_model.LicenseType.objects.all().order_by('-id')
    serializer_class = licensetype_serializer.LicenseTypeSerializer

# SubDivisonApi for creating
class SubDivisonApi(generics.ListCreateAPIView):
    queryset = masters_model.Subdivision.objects.all()  # Added queryset
    serializer_class = placemaster_serializer.SubDivisonSerializer

    def post(self, request, format=None):
        serializer = placemaster_serializer.SubDivisonSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)

# DistrictAdd for listing, creating, and updating
class DistrictAdd(generics.ListCreateAPIView):

    queryset = masters_model.District.objects.all()  # Added queryset
    serializer_class = placemaster_serializer.DistrictSerializer

    def post(self, request, format=None):
        serializer = placemaster_serializer.DistrictSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, id, format=None):
        district = masters_model.District.objects.get(id=id)
        serializer = placemaster_serializer.DistrictSerializer(district, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# DistrictView for listing and retrieving a specific district
class DistrictView(generics.ListCreateAPIView):
    queryset = masters_model.District.objects.all()  # Added queryset
    serializer_class = placemaster_serializer.DistrictSerializer

    def get(self, request, pk=None, format=None):
        if pk:
            district = masters_model.District.objects.get(id=pk)
            serializer = placemaster_serializer.DistrictSerializer(district)
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        districts = masters_model.District.objects.all()
        serializer = placemaster_serializer.DistrictSerializer(districts, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

# PoliceStationAPI for listing, creating, and updating
class PoliceStationAPI(generics.ListCreateAPIView):
    queryset = masters_model.PoliceStation.objects.all()  # Added queryset
    serializer_class = placemaster_serializer.PoliceStationSerializer


    def post(self, request, format=None):
        serializer = placemaster_serializer.PoliceStationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    def get(self, request, pk=None, format=None):
        if pk:
            policestation = masters_model.PoliceStation.objects.get(id=pk)
            serializer = placemaster_serializer.PoliceStationSerializer(policestation)
            return response.Response(serializer.data, status=status.HTTP_200_OK)

        police_stations = masters_model.PoliceStation.objects.all()
        serializer = placemaster_serializer.PoliceStationSerializer(police_stations, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)



    def put(self, request, id, format=None):
        policestation = masters_model.PoliceStation.objects.get(id=id)
        serializer = placemaster_serializer.PoliceStationSerializer(policestation, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
