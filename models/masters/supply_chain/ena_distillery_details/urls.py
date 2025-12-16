from django.urls import path
from . import views

app_name = 'ena_distillery_details'

urlpatterns = [
    path('', views.enaDistilleryTypesListAPIView.as_view(), name='ena-distillery-types-list'),
]

