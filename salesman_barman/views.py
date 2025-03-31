from django.views import View
from django.http import JsonResponse

from .models import SalesmanBarmanDetails, DocumentsDetails
from .serializers import SalesmanBarmanDetailsSerializer, DocumentsDetailsSerializer



class SalesmanCreateView(View):
    def post(self , request , *args , **kwargs):
        
