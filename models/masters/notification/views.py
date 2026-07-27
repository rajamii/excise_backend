from django.http import FileResponse, Http404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer


# Create Notification API
class NotificationCreateAPIView(generics.CreateAPIView):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]


# Notification List API
class NotificationListAPIView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.all()
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        return queryset


# Public Notification List API
class NotificationPublicListAPIView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = Notification.objects.filter(is_active=True)
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        limit = self.request.query_params.get('limit')
        if limit:
            try:
                return queryset[:int(limit)]
            except (TypeError, ValueError):
                return queryset
        return queryset


class NotificationDownloadAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, is_active=True)
        except Notification.DoesNotExist as exc:
            raise Http404('Notification file not found.') from exc

        if not notification.notification_file:
            raise Http404('Notification file not found.')

        return FileResponse(
            notification.notification_file.open('rb'),
            as_attachment=True,
            filename=notification.notification_file.name.split('/')[-1],
        )


# View Notification API
class NotificationDetailAPIView(generics.RetrieveAPIView):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]


# Update Notification API
class NotificationUpdateAPIView(generics.UpdateAPIView):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]


# Delete Notification API
class NotificationDeleteAPIView(generics.DestroyAPIView):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
