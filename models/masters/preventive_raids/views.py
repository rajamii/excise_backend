from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import PreventiveRaid, PreventiveRaidImage
from .serializers import PreventiveRaidSerializer


class PreventiveRaidCreateAPIView(generics.CreateAPIView):
    queryset = PreventiveRaid.objects.all()
    serializer_class = PreventiveRaidSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        raid = serializer.save()
        uploaded_images = self.request.FILES.getlist('uploaded_images')
        for img in uploaded_images:
            PreventiveRaidImage.objects.create(raid=raid, image=img)


class PreventiveRaidListAPIView(generics.ListAPIView):
    queryset = PreventiveRaid.objects.all()
    serializer_class = PreventiveRaidSerializer
    permission_classes = [AllowAny]


class PreventiveRaidDetailAPIView(generics.RetrieveAPIView):
    queryset = PreventiveRaid.objects.all()
    serializer_class = PreventiveRaidSerializer
    permission_classes = [AllowAny]


class PreventiveRaidUpdateAPIView(generics.UpdateAPIView):
    queryset = PreventiveRaid.objects.all()
    serializer_class = PreventiveRaidSerializer
    permission_classes = [IsAuthenticated]

    def perform_update(self, serializer):
        raid = serializer.save()
        uploaded_images = self.request.FILES.getlist('uploaded_images')
        if uploaded_images:
            # Delete old images and add the new ones
            raid.images.all().delete()
            for img in uploaded_images:
                PreventiveRaidImage.objects.create(raid=raid, image=img)


class PreventiveRaidDeleteAPIView(generics.DestroyAPIView):
    queryset = PreventiveRaid.objects.all()
    serializer_class = PreventiveRaidSerializer
    permission_classes = [IsAuthenticated]
