from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from rest_framework import generics
from .models import LicenseApplication
from .serializers import LicenseApplicationSerializer
from .services.workflow import advance_application


class LicenseApplicationCreateView(generics.CreateAPIView):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer

class LicenseApplicationListView(generics.ListAPIView):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer

class LicenseApplicationDetailView(generics.RetrieveAPIView):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer

    @action(detail=True, methods=['post'], url_path='advance')
    def advance(self, request, pk=None):
        """
        Advance the license application to the next stage
        based on the current user's role.
        """
        application = self.get_object()
        user = request.user
        remarks = request.data.get("remarks", "")

        try:
            advance_application(application, user, remarks)
            return Response({"detail": "Application advanced successfully."}, status=status.HTTP_200_OK)
        except ValidationError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
