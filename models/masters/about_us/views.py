from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import HeadOfOrganisation, ExciseSecretary
from .serializers import HeadOfOrganisationSerializer, ExciseSecretarySerializer


# Create HeadOfOrganisation API
class HeadOfOrganisationCreateAPIView(generics.CreateAPIView):
    queryset = HeadOfOrganisation.objects.all()
    serializer_class = HeadOfOrganisationSerializer
    permission_classes = [IsAuthenticated]


# HeadOfOrganisation List API
class HeadOfOrganisationListAPIView(generics.ListAPIView):
    queryset = HeadOfOrganisation.objects.all()
    serializer_class = HeadOfOrganisationSerializer
    permission_classes = [AllowAny]


# View HeadOfOrganisation API
class HeadOfOrganisationDetailAPIView(generics.RetrieveAPIView):
    queryset = HeadOfOrganisation.objects.all()
    serializer_class = HeadOfOrganisationSerializer
    permission_classes = [IsAuthenticated]


# Update HeadOfOrganisation API
class HeadOfOrganisationUpdateAPIView(generics.UpdateAPIView):
    queryset = HeadOfOrganisation.objects.all()
    serializer_class = HeadOfOrganisationSerializer
    permission_classes = [IsAuthenticated]


# Delete HeadOfOrganisation API
class HeadOfOrganisationDeleteAPIView(generics.DestroyAPIView):
    queryset = HeadOfOrganisation.objects.all()
    serializer_class = HeadOfOrganisationSerializer
    permission_classes = [IsAuthenticated]


# Create ExciseSecretary API
class ExciseSecretaryCreateAPIView(generics.CreateAPIView):
    queryset = ExciseSecretary.objects.all()
    serializer_class = ExciseSecretarySerializer
    permission_classes = [IsAuthenticated]


# ExciseSecretary List API
class ExciseSecretaryListAPIView(generics.ListAPIView):
    queryset = ExciseSecretary.objects.all()
    serializer_class = ExciseSecretarySerializer
    permission_classes = [AllowAny]


# View ExciseSecretary API
class ExciseSecretaryDetailAPIView(generics.RetrieveAPIView):
    queryset = ExciseSecretary.objects.all()
    serializer_class = ExciseSecretarySerializer
    permission_classes = [IsAuthenticated]


# Update ExciseSecretary API
class ExciseSecretaryUpdateAPIView(generics.UpdateAPIView):
    queryset = ExciseSecretary.objects.all()
    serializer_class = ExciseSecretarySerializer
    permission_classes = [IsAuthenticated]


# Delete ExciseSecretary API
class ExciseSecretaryDeleteAPIView(generics.DestroyAPIView):
    queryset = ExciseSecretary.objects.all()
    serializer_class = ExciseSecretarySerializer
    permission_classes = [IsAuthenticated]

