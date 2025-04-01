from django.urls import path 
from .views import (
    CompanyDetailsList ,
    CompanyDetailsDetail ,
    MemberDetailsList ,
    MemberDetailsDetail ,
    DocumentDetailsList ,
    DocumentDetailsDetail ,
)

urlpatterns = [
    path('companies/list/', CompanyDetailsList.as_view(), name='companydetails-list'),
    path('companies/create/', CompanyDetailsList.as_view(), name='companydetails-list'),
    
    path('companies/detail/<int:pk>/', CompanyDetailsDetail.as_view(), name='companydetails-detail'),
    path('companies/update/<int:pk>/', CompanyDetailsDetail.as_view(), name='companydetails-detail'),
    path('companies/delete/<int:pk>/', CompanyDetailsDetail.as_view(), name='companydetails-detail'),
    

    path('members/list/', MemberDetailsList.as_view(), name='memberdetails-list'),
    path('members/create/', MemberDetailsList.as_view(), name='memberdetails-list'),
    
    path('members/detail/<int:pk>/', MemberDetailsDetail.as_view(), name='memberdetails-detail'),
    path('members/update/<int:pk>/', MemberDetailsDetail.as_view(), name='memberdetails-detail'),
    path('members/delete/<int:pk>/', MemberDetailsDetail.as_view(), name='memberdetails-detail'),
    

    path('documents/list/', DocumentDetailsList.as_view(), name='documentdetails-list'),
    path('documents/create/', DocumentDetailsList.as_view(), name='documentdetails-list'),
    
    path('documents/detail/<int:pk>/', DocumentDetailsDetail.as_view(), name='documentdetails-detail'),
    path('documents/update/<int:pk>/', DocumentDetailsDetail.as_view(), name='documentdetails-detail'),
    path('documents/delete/<int:pk>/', DocumentDetailsDetail.as_view(), name='documentdetails-detail'),
    
]
