from django.urls import path
from . import views

app_name = "site_enquiry"

urlpatterns = [
    path('<str:application_id>/site-enquiry/', views.site_enquiry_detail, name='site-enquiry-detail'),
]