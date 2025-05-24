from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from rest_framework import generics
from .models import LicenseApplication
from .serializers import LicenseApplicationSerializer
from .services.workflow import advance_application
from .models import LicenseApplicationTransaction

# View to handle creation of license applications
class LicenseApplicationCreateView(generics.CreateAPIView):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer

    def perform_create(self, serializer):
        # Save the application and set the initial stage to 'permit_section'
        application = serializer.save(current_stage='permit_section')
        # Log the transaction for the created application
        LicenseApplicationTransaction.objects.create(
            license_application=application,
            performed_by=self.request.user,
            stage='permit_section',
            remarks='License Applied'
        )

# View to list all license applications
class LicenseApplicationListView(generics.ListAPIView):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer

# View to retrieve details of a specific license application
class LicenseApplicationDetailView(generics.RetrieveAPIView):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer

# View to update a specific license application
class LicenseApplicationUpdateView(generics.UpdateAPIView):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer
    lookup_field = 'pk'

class LicenseApplicationDeleteView(generics.DestroyAPIView):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer
    lookup_field = 'pk'

    def perform_destroy(self, instance):
        # Delete all related transactions first
        LicenseApplicationTransaction.objects.filter(license_application=instance).delete()
        # Then delete the application itself
        instance.delete()

# View to handle advancing the application to the next stage
class LicenseApplicationAdvanceView(APIView):
    def post(self, request, pk):
        try:
            # Fetch the application by primary key
            application = LicenseApplication.objects.get(pk=pk)
        except LicenseApplication.DoesNotExist:
            return Response({"detail": "Application not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        action = request.data.get("action", "")
        remarks = request.data.get("remarks", "")

        try:
            # Advance the application using the workflow service
            advance_application(application, user, action, remarks)
            return Response({"detail": "Application advanced successfully."}, status=status.HTTP_200_OK)
        except ValidationError as ve:
            # Handle validation errors
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)

# View to fetch dashboard counts based on the user's role
class DashboardCountsView(APIView):
    def get(self, request):
        role = request.user.role

        if role == 'permit_section':
            # Fetch counts for applications in 'permit_section' stage
            pending_count = LicenseApplication.objects.filter(current_stage='permit_section').count()
            approved_count = LicenseApplication.objects.filter(current_stage__in=['commissioner', 'joint_commissioner']).count()
            rejected_by_permit_section_count = LicenseApplication.objects.filter(current_stage='rejected_by_permit_section').count()

            return Response({
                "pending": pending_count,
                "approved": approved_count,
                "rejected": rejected_by_permit_section_count
            })
        elif role == 'joint_commissioner' or role == 'commissioner':
            # Fetch counts for applications forwarded to higher authorities
            pending_count = LicenseApplication.objects.filter(current_stage__in=['commissioner', 'joint_commissioner']).count()
            approved_count = LicenseApplication.objects.filter(current_stage='approved').count()
            rejected_by_me = LicenseApplication.objects.filter(current_stage=f'rejected_by_{role}').count()

            return Response({
                "pending": pending_count,
                "approved": approved_count,
                "rejected": rejected_by_me
            })
        elif role == 'licensee':
            # Fetch counts for applications submitted by the licensee
            applied_count = LicenseApplication.objects.filter(current_stage='permit_section').count()
            pending_count = LicenseApplication.objects.filter(current_stage__in=['commissioner', 'joint_commissioner']).count()
            approved_count = LicenseApplication.objects.filter(current_stage='approved', is_approved=True).count()
            rejected_count = LicenseApplication.objects.filter(current_stage__in=['rejected_by_permit_section', 'rejected_by_commissioner', 'rejected_by_joint_commissioner']).count()

            return Response({
                "applied": applied_count,
                "pending": pending_count,
                "approved": approved_count,
                "rejected": rejected_count
            })
        else:
            # Handle invalid roles
            return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

# View to fetch application lists based on the user's role
class ApplicationListView(APIView):
    def get(self, request):
        role = request.user.role

        if role == 'permit_section':
            # Fetch applications for 'permit_section' role
            pending_apps = LicenseApplication.objects.filter(current_stage='permit_section')
            approved_apps = LicenseApplication.objects.filter(current_stage__in=['commissioner', 'joint_commissioner'])
            rejected_by_permit_section_apps = LicenseApplication.objects.filter(current_stage='rejected_by_permit_section', is_approved=False)
        
            return Response({
                "pending": LicenseApplicationSerializer(pending_apps, many=True).data,
                "approved": LicenseApplicationSerializer(approved_apps, many=True).data,
                "rejected": LicenseApplicationSerializer(rejected_by_permit_section_apps, many=True).data,
            })

        elif role in ['joint_commissioner', 'commissioner']:
            # Fetch applications for 'joint_commissioner' or 'commissioner' roles
            pending_apps = LicenseApplication.objects.filter(current_stage__in=['commissioner', 'joint_commissioner'])
            approved_apps = LicenseApplication.objects.filter(current_stage='approved')
            rejected_by_me = LicenseApplication.objects.filter(current_stage__in=['rejected_by_commissioner', 'rejected_by_joint_commissioner'])

            return Response({
                "pending": LicenseApplicationSerializer(pending_apps, many=True).data,
                "approved": LicenseApplicationSerializer(approved_apps, many=True).data,
                "rejected": LicenseApplicationSerializer(rejected_by_me, many=True).data
            })
        
        elif role == 'licensee':
            # Fetch applications for 'licensee' role
            applied_apps = LicenseApplication.objects.filter(current_stage='permit_section')
            pending_apps = LicenseApplication.objects.filter(current_stage__in=['commissioner', 'joint_commissioner'])
            approved_apps = LicenseApplication.objects.filter(current_stage='approved')
            rejected_apps = LicenseApplication.objects.filter(current_stage__in=['rejected_by_permit_section', 'rejected_by_commissioner', 'rejected_by_joint_commissioner'])

            return Response({
                "applied": LicenseApplicationSerializer(applied_apps, many=True).data,
                "pending": LicenseApplicationSerializer(pending_apps, many=True).data,
                "approved": LicenseApplicationSerializer(approved_apps, many=True).data,
                "rejected": LicenseApplicationSerializer(rejected_apps, many=True).data
            })

        # Handle invalid roles
        return Response({"detail": "Invalid role"}, status=400)
