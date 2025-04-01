from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .models import NodalOfficer, PublicInformationOfficer, DirectorateAndDistrictOfficials, GrievanceRedressalOfficer
from .serializers import NodalOfficerSerializer, PublicInformationOfficerSerializer, DirectorateAndDistrictOfficialsSerializer, GrievanceRedressalOfficerSerializer

# Create NodalOfficer API
class NodalOfficerCreateAPIView(generics.CreateAPIView):
    queryset = NodalOfficer.objects.all()
    serializer_class = NodalOfficerSerializer
    permission_classes = [IsAuthenticated]

# View NodalOfficer API
class NodalOfficerDetailAPIView(generics.RetrieveAPIView):
    queryset = NodalOfficer.objects.all()
    serializer_class = NodalOfficerSerializer
    permission_classes = [IsAuthenticated]

# Update NodalOfficer API
class NodalOfficerUpdateAPIView(generics.UpdateAPIView):
    queryset = NodalOfficer.objects.all()
    serializer_class = NodalOfficerSerializer
    permission_classes = [IsAuthenticated]

# Delete NodalOfficer API
class NodalOfficerDeleteAPIView(generics.DestroyAPIView):
    queryset = NodalOfficer.objects.all()
    serializer_class = NodalOfficerSerializer
    permission_classes = [IsAuthenticated]

# Create PublicInformationOfficer API
class PublicInformationOfficerCreateAPIView(generics.CreateAPIView):
    queryset = PublicInformationOfficer.objects.all()
    serializer_class = PublicInformationOfficerSerializer
    permission_classes = [IsAuthenticated]

# View PublicInformationOfficer API
class PublicInformationOfficerDetailAPIView(generics.RetrieveAPIView):
    queryset = PublicInformationOfficer.objects.all()
    serializer_class = PublicInformationOfficerSerializer
    permission_classes = [IsAuthenticated]

# Update PublicInformationOfficer API
class PublicInformationOfficerUpdateAPIView(generics.UpdateAPIView):
    queryset = PublicInformationOfficer.objects.all()
    serializer_class = PublicInformationOfficerSerializer
    permission_classes = [IsAuthenticated]

# Delete PublicInformationOfficer API
class PublicInformationOfficerDeleteAPIView(generics.DestroyAPIView):
    queryset = PublicInformationOfficer.objects.all()
    serializer_class = PublicInformationOfficerSerializer
    permission_classes = [IsAuthenticated]

# Create DirectorateAndDistrictOfficials API
class DirectorateAndDistrictOfficialsCreateAPIView(generics.CreateAPIView):
    queryset = DirectorateAndDistrictOfficials.objects.all()
    serializer_class = DirectorateAndDistrictOfficialsSerializer
    permission_classes = [IsAuthenticated]

# View DirectorateAndDistrictOfficials API
class DirectorateAndDistrictOfficialsDetailAPIView(generics.RetrieveAPIView):
    queryset = DirectorateAndDistrictOfficials.objects.all()
    serializer_class = DirectorateAndDistrictOfficialsSerializer
    permission_classes = [IsAuthenticated]

# Update DirectorateAndDistrictOfficials API
class DirectorateAndDistrictOfficialsUpdateAPIView(generics.UpdateAPIView):
    queryset = DirectorateAndDistrictOfficials.objects.all()
    serializer_class = DirectorateAndDistrictOfficialsSerializer
    permission_classes = [IsAuthenticated]

# Delete DirectorateAndDistrictOfficials API
class DirectorateAndDistrictOfficialsDeleteAPIView(generics.DestroyAPIView):
    queryset = DirectorateAndDistrictOfficials.objects.all()
    serializer_class = DirectorateAndDistrictOfficialsSerializer
    permission_classes = [IsAuthenticated]

# Create GrievanceRedressalOfficer API
class GrievanceRedressalOfficerCreateAPIView(generics.CreateAPIView):
    queryset = GrievanceRedressalOfficer.objects.all()
    serializer_class = GrievanceRedressalOfficerSerializer
    permission_classes = [IsAuthenticated]

# View GrievanceRedressalOfficer API
class GrievanceRedressalOfficerDetailAPIView(generics.RetrieveAPIView):
    queryset = GrievanceRedressalOfficer.objects.all()
    serializer_class = GrievanceRedressalOfficerSerializer
    permission_classes = [IsAuthenticated]

# Update GrievanceRedressalOfficer API
class GrievanceRedressalOfficerUpdateAPIView(generics.UpdateAPIView):
    queryset = GrievanceRedressalOfficer.objects.all()
    serializer_class = GrievanceRedressalOfficerSerializer
    permission_classes = [IsAuthenticated]

# Delete GrievanceRedressalOfficer API
class GrievanceRedressalOfficerDeleteAPIView(generics.DestroyAPIView):
    queryset = GrievanceRedressalOfficer.objects.all()
    serializer_class = GrievanceRedressalOfficerSerializer
    permission_classes = [IsAuthenticated]
