from rest_framework import generics, response, status
from masters import models as masters_model
from masters.serializers import (licensecategory_serializer, licensetype_serializer, placemaster_serializer)
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator


# LicenseCategoryList for listing , creating , Updating and Deleting 


class LicenseCategoryAPI ( generics.ListCreateAPIView , generics.RetrieveUpdateDestroyAPIView):

    queryset = masters_model.LicenseCategory.objects.all()
    serializer_class = licensecategory_serializer.LicenseCategorySerializer
    lookup_field = 'id'


    def post(self , request , format=None):
        serializer = licensecategory_serializer.LicenseCategorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


        
    def get(self, request, id=None, format=None):

        if id:
            license_category = masters_model.LicenseCategory.objects.get(id=id)
            serializer = licensecategory_serializer.LicenseCategorySerializer(license_category)
            return response.Response(serializer.data, status=status.HTTP_200_OK)

        license_categories = masters_model.LicenseCategory.objects.all()
        serializer = licensecategory_serializer.LicenseCategorySerializer(license_categories, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)




    def put(self, request, id, format=None):
        license_category = masters_model.LicenseCategory.objects.get(id=id)
        serializer = licensecategory_serializer.LicenseCategorySerializer(license_category, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_200_OK)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




    def delete(self, request, id, format=None):
        try:
            license_category = masters_model.LicenseCategory.objects.get(id=id)
            license_category.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.LicenseCategory.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)


# LicenseTypeList for listing , creating , Updating and Deleting 


class LicenseTypeAPI (generics.ListCreateAPIView , generics.RetrieveUpdateDestroyAPIView):

    queryset = masters_model.LicenseType.objects.all()
    serializer_class = licensetype_serializer.LicenseTypeSerializer
    lookup_field = 'id'

    def post (self , request , forman=None):
        serializer = licensetype_serializer.LicenseTypeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    
    def get(self, request, id=None, format=None):
        if id:
            try:
                license_type = masters_model.LicenseType.objects.get(id=id)
                serializer = self.serializer_class(license_type)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_model.LicenseType.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)

        license_types = masters_model.LicenseType.objects.all()
        serializer = self.serializer_class(license_types, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)



    def put(self, request, id, format=None):
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
        try:
            license_type = masters_model.LicenseType.objects.get(id=id)
            license_type.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.LicenseType.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)
        
            

#SubDivisonApi for creating
class SubDivisonApi(generics.ListCreateAPIView , generics.RetrieveUpdateDestroyAPIView):

    queryset = masters_model.Subdivision.objects.all()  # Added queryset
    serializer_class = placemaster_serializer.SubDivisonSerializer
    lookup_field = 'id'

     
    def post(self, request, format=None):
        serializer = placemaster_serializer.SubDivisonSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors ,  stats=status.HTTP_400_BAD_REQUEST)


    
    def get(self, request, id=None, dc=None, format=None):
        if id:
            try:
                subdivision = masters_model.Subdivision.objects.get(id=id)
                serializer = self.serializer_class(subdivision)
                return response.Response(serializer.data, status=status.HTTP_200_OK)

            except masters_model.Subdivision.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)

        if dc is not None:  # Changed district_code to dc for consistency

            subdivisions = masters_model.Subdivision.objects.filter(DistrictCode=dc) 

            if not subdivisions.exists():
                raise NotFound(detail="No subdivisions found for this district code", code=status.HTTP_404_NOT_FOUND)

            serializer = self.serializer_class(subdivisions, many=True)
            return response.Response(serializer.data, status=status.HTTP_200_OK)


        subdivisions = masters_model.Subdivision.objects.all()
        serializer = self.serializer_class(subdivisions, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)


     
    def put(self, request, id, format=None):
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
        try:
            subdivision = masters_model.Subdivision.objects.get(id=id)
            subdivision.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.Subdivision.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)


#DistrictAdd for listing, creating, and updating



class DistrictAPI(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = masters_model.District.objects.all()
    serializer_class = placemaster_serializer.DistrictSerializer
    lookup_field = 'id'

    def post(self, request, format=None):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    
    def get(self, request, id=None, format=None):
        if id:
            try:
                district = masters_model.District.objects.get(id=id)
                serializer = self.serializer_class(district)
                return response.Response(serializer.data, status=status.HTTP_200_OK)
            except masters_model.District.DoesNotExist:
                return response.Response(status=status.HTTP_404_NOT_FOUND)

        districts = masters_model.District.objects.all()
        serializer = self.serializer_class(districts, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)


    
    def put(self, request, id, format=None):
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
        try:
            district = masters_model.District.objects.get(id=id)
            district.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except masters_model.District.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)


    
# PoliceStationAPI for listing, creating, updating and deleting 


class PoliceStationAPI(generics.ListCreateAPIView , generics.RetrieveUpdateDestroyAPIView):

    queryset = masters_model.PoliceStation.objects.all()  # Added queryset
    serializer_class = placemaster_serializer.PoliceStationSerializer
    lookup_field = 'id'

    
    def post(self, request, format=None):
        serializer = placemaster_serializer.PoliceStationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    
    def get(self, request, id=None, format=None):
        if id:
            policestation = masters_model.PoliceStation.objects.get(id=id)
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


    
    def delete(self , request , id , format=None ):

        try:
            policestation = masters_model.PoliceStation.objects.get(id=id)
            policestation.delete()
            return response.Response(status=status.HTTP_205_RESET_CONTENT)
        except masters_model.PoliceStation.DoesNotExist:
            return response.Response(stats=status.HTTP_404_NOT_FOUND)
        
