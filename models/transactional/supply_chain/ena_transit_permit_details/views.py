from rest_framework import status, views, generics
from rest_framework.response import Response
from .serializers import TransitPermitSubmissionSerializer, EnaTransitPermitDetailSerializer
from .models import EnaTransitPermitDetail


class SubmitTransitPermitAPIView(views.APIView):
    def post(self, request):
        print(f"DEBUG: Raw Request Data keys: {list(request.data.keys())}")
        print(f"DEBUG: Full Request Data: {request.data}")
        serializer = TransitPermitSubmissionSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            bill_no = data['bill_no']
            
            # 1. Uniqueness Check (Application Level)
            if EnaTransitPermitDetail.objects.filter(bill_no=bill_no).exists():
                return Response({
                    "status": "error",
                    "message": "Submission failed. Bill Number already exists."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 2. Prepare common data
            sole_distributor_name = data['sole_distributor']
            date = data['date']
            depot_address = data['depot_address']
            vehicle_number = data['vehicle_number']
            products = data['products'] 
            
            # Determine Licensee ID
            licensee_id = None
            if hasattr(request.user, 'supply_chain_profile'):
                licensee_id = request.user.supply_chain_profile.licensee_id
            
            created_records = []
            
            # 3. Save each product as a new row
            try:
                for product in products:
                    obj = EnaTransitPermitDetail(
                        bill_no=bill_no,
                        sole_distributor_name=sole_distributor_name,
                        date=date,
                        depot_address=depot_address,
                        vehicle_number=vehicle_number,
                        licensee_id=licensee_id,
                        
                        brand=product.get('brand'),
                        size_ml=product.get('size'), 
                        cases=product.get('cases'),

                        # New fields
                        brand_owner=product.get('brand_owner', ''),
                        liquor_type=product.get('liquor_type', ''),
                        exfactory_price_rs_per_case=product.get('ex_factory_price', 0.00),
                        
                        excise_duty_rs_per_case=product.get('excise_duty', 0.00),
                        education_cess_rs_per_case=product.get('education_cess', 0.00),
                        additional_excise_duty_rs_per_case=product.get('additional_excise', 0.00),
                        
                        manufacturing_unit_name=product.get('manufacturing_unit_name', ''),

                        # Calculated totals
                        total_excise_duty=float(product.get('excise_duty', 0.00)) * int(product.get('cases', 0)),
                        total_education_cess=float(product.get('education_cess', 0.00)) * int(product.get('cases', 0)),
                        total_additional_excise=float(product.get('additional_excise', 0.00)) * int(product.get('cases', 0)),
                        total_amount=(
                            (float(product.get('excise_duty', 0.00)) + 
                             float(product.get('education_cess', 0.00)) + 
                             float(product.get('additional_excise', 0.00))) * int(product.get('cases', 0))
                        )
                    )

                    obj.save()
                    created_records.append(obj)
                
                return Response({
                    "status": "success",
                    "message": "Transit Permit Submitted Successfully",
                    "count": len(created_records)
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                 return Response({
                    "status": "error",
                    "message": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        print(f"Validation Errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class GetTransitPermitAPIView(generics.ListAPIView):
    queryset = EnaTransitPermitDetail.objects.all()
    serializer_class = EnaTransitPermitDetailSerializer

