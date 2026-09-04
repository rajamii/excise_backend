from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import (
    HeadOfOrganisation,
    ExciseSecretary,
    AboutUs,
    Department,
    ProductsServices,
    RefundCancellationPolicy
)
from .serializers import (
    HeadOfOrganisationSerializer,
    ExciseSecretarySerializer,
    AboutUsSerializer,
    DepartmentSerializer,
    ProductsServicesSerializer,
    RefundCancellationPolicySerializer
)



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


# Create AboutUs API
class AboutUsCreateAPIView(generics.CreateAPIView):
    queryset = AboutUs.objects.all()
    serializer_class = AboutUsSerializer
    permission_classes = [IsAuthenticated]


# AboutUs List API
class AboutUsListAPIView(generics.ListAPIView):
    serializer_class = AboutUsSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = AboutUs.objects.all()
        page_key = self.request.query_params.get('page_key')
        if page_key:
            queryset = queryset.filter(page_key=page_key)
        return queryset


# View AboutUs API
class AboutUsDetailAPIView(generics.RetrieveAPIView):
    queryset = AboutUs.objects.all()
    serializer_class = AboutUsSerializer
    permission_classes = [AllowAny]


# Update AboutUs API
class AboutUsUpdateAPIView(generics.UpdateAPIView):
    queryset = AboutUs.objects.all()
    serializer_class = AboutUsSerializer
    permission_classes = [IsAuthenticated]


# Delete AboutUs API
class AboutUsDeleteAPIView(generics.DestroyAPIView):
    queryset = AboutUs.objects.all()
    serializer_class = AboutUsSerializer
    permission_classes = [IsAuthenticated]


# ===================== DEPARTMENT APIS =====================

class DepartmentCreateAPIView(generics.CreateAPIView):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]


class DepartmentListAPIView(generics.ListAPIView):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [AllowAny]


class DepartmentDetailAPIView(generics.RetrieveAPIView):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [AllowAny]


class DepartmentUpdateAPIView(generics.UpdateAPIView):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]


class DepartmentDeleteAPIView(generics.DestroyAPIView):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]


# ===================== PRODUCTS & SERVICES APIS =====================

class ProductsServicesCreateAPIView(generics.CreateAPIView):
    queryset = ProductsServices.objects.all()
    serializer_class = ProductsServicesSerializer
    permission_classes = [IsAuthenticated]


class ProductsServicesListAPIView(generics.ListAPIView):
    queryset = ProductsServices.objects.all()
    serializer_class = ProductsServicesSerializer
    permission_classes = [AllowAny]


class ProductsServicesDetailAPIView(generics.RetrieveAPIView):
    queryset = ProductsServices.objects.all()
    serializer_class = ProductsServicesSerializer
    permission_classes = [AllowAny]


class ProductsServicesUpdateAPIView(generics.UpdateAPIView):
    queryset = ProductsServices.objects.all()
    serializer_class = ProductsServicesSerializer
    permission_classes = [IsAuthenticated]


class ProductsServicesDeleteAPIView(generics.DestroyAPIView):
    queryset = ProductsServices.objects.all()
    serializer_class = ProductsServicesSerializer
    permission_classes = [IsAuthenticated]


# ===================== REFUND & CANCELLATION POLICY APIS =====================

class RefundCancellationPolicyCreateAPIView(generics.CreateAPIView):
    queryset = RefundCancellationPolicy.objects.all()
    serializer_class = RefundCancellationPolicySerializer
    permission_classes = [IsAuthenticated]


class RefundCancellationPolicyListAPIView(generics.ListAPIView):
    queryset = RefundCancellationPolicy.objects.all()
    serializer_class = RefundCancellationPolicySerializer
    permission_classes = [AllowAny]


class RefundCancellationPolicyDetailAPIView(generics.RetrieveAPIView):
    queryset = RefundCancellationPolicy.objects.all()
    serializer_class = RefundCancellationPolicySerializer
    permission_classes = [AllowAny]


class RefundCancellationPolicyUpdateAPIView(generics.UpdateAPIView):
    queryset = RefundCancellationPolicy.objects.all()
    serializer_class = RefundCancellationPolicySerializer
    permission_classes = [IsAuthenticated]


class RefundCancellationPolicyDeleteAPIView(generics.DestroyAPIView):
    queryset = RefundCancellationPolicy.objects.all()
    serializer_class = RefundCancellationPolicySerializer
    permission_classes = [IsAuthenticated]



