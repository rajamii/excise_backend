from django.urls import path
from . import views

urlpatterns = [
    # Nodal Officer APIs
    path('nodalofficer/create/', views.NodalOfficerCreateAPIView.as_view(), name='nodalofficer-create'),
    path('nodalofficer/detail/<int:pk>/', views.NodalOfficerDetailAPIView.as_view(), name='nodalofficer-detail'),
    path('nodalofficer/update/<int:pk>/', views.NodalOfficerUpdateAPIView.as_view(), name='nodalofficer-update'),
    path('nodalofficer/delete/<int:pk>/', views.NodalOfficerDeleteAPIView.as_view(), name='nodalofficer-delete'),

    # Public Information Officer APIs
    path('publicinformationofficer/create/', views.PublicInformationOfficerCreateAPIView.as_view(), name='publicinformationofficer-create'),
    path('publicinformationofficer/detail/<int:pk>/', views.PublicInformationOfficerDetailAPIView.as_view(), name='publicinformationofficer-detail'),
    path('publicinformationofficer/update/<int:pk>/', views.PublicInformationOfficerUpdateAPIView.as_view(), name='publicinformationofficer-update'),
    path('publicinformationofficer/delete/<int:pk>/', views.PublicInformationOfficerDeleteAPIView.as_view(), name='publicinformationofficer-delete'),

    # Directorate and District Officials APIs
    path('directoratendistrictofficials/create/', views.DirectorateAndDistrictOfficialsCreateAPIView.as_view(), name='directoratendistrictofficials-create'),
    path('directoratendistrictofficials/detail/<int:pk>/', views.DirectorateAndDistrictOfficialsDetailAPIView.as_view(), name='directoratendistrictofficials-detail'),
    path('directoratendistrictofficials/update/<int:pk>/', views.DirectorateAndDistrictOfficialsUpdateAPIView.as_view(), name='directoratendistrictofficials-update'),
    path('directoratendistrictofficials/delete/<int:pk>/', views.DirectorateAndDistrictOfficialsDeleteAPIView.as_view(), name='directoratendistrictofficials-delete'),

    # Grievance Redressal Officer APIs
    path('grievanceredressalofficer/create/', views.GrievanceRedressalOfficerCreateAPIView.as_view(), name='grievanceredressalofficer-create'),
    path('grievanceredressalofficer/detail/<int:pk>/', views.GrievanceRedressalOfficerDetailAPIView.as_view(), name='grievanceredressalofficer-detail'),
    path('grievanceredressalofficer/update/<int:pk>/', views.GrievanceRedressalOfficerUpdateAPIView.as_view(), name='grievanceredressalofficer-update'),
    path('grievanceredressalofficer/delete/<int:pk>/', views.GrievanceRedressalOfficerDeleteAPIView.as_view(), name='grievanceredressalofficer-delete'),
]
