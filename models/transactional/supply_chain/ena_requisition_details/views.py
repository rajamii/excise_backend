from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import re
from .models import EnaRequisitionDetail
from .serializers import EnaRequisitionDetailSerializer


class EnaRequisitionDetailListCreateAPIView(generics.ListCreateAPIView):
    queryset = EnaRequisitionDetail.objects.all()
    serializer_class = EnaRequisitionDetailSerializer


class EnaRequisitionDetailRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = EnaRequisitionDetail.objects.all()
    serializer_class = EnaRequisitionDetailSerializer


class GetNextRefNumberAPIView(APIView):
    """
    API endpoint to generate the next unique reference number.
    Format: IBPS/{number:02d}/EXCISE
    
    Logic:
    - Queries all existing our_ref_no values
    - Extracts numeric parts and finds the maximum
    - Returns next sequential number
    - If all records are deleted, restarts from 1
    """
    def get(self, request):
        try:
            # Get all existing reference numbers
            existing_refs = EnaRequisitionDetail.objects.values_list('our_ref_no', flat=True)
            
            # Extract numeric parts from reference numbers
            numbers = []
            pattern = r'IBPS/(\d+)/EXCISE'
            
            for ref in existing_refs:
                match = re.match(pattern, ref)
                if match:
                    numbers.append(int(match.group(1)))
            
            # Determine next number
            if numbers:
                next_number = max(numbers) + 1
            else:
                next_number = 1
            
            # Format the reference number
            ref_number = f"IBPS/{next_number:02d}/EXCISE"
            
            return Response({
                'status': 'success',
                'ref_number': ref_number,
                'next_sequence': next_number
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateRequisitionStatusAPIView(APIView):
    """
    API endpoint to update a requisition's status dynamically.
    Accepts 'status_code' in request body.
    """
    def post(self, request, pk):
        try:
            from models.masters.supply_chain.status_master.models import StatusMaster
            
            status_code = request.data.get('status_code')
            if not status_code:
                return Response({
                    'status': 'error',
                    'message': 'status_code is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get the requisition
            requisition = EnaRequisitionDetail.objects.get(pk=pk)
            
            # Get the status from status_master
            new_status = StatusMaster.objects.get(status_code=status_code)
            
            # Update the requisition status
            requisition.status = new_status.status_name
            requisition.status_code = new_status.status_code
            requisition.save()
            
            # Return updated requisition
            serializer = EnaRequisitionDetailSerializer(requisition)
            
            return Response({
                'status': 'success',
                'message': f'Requisition status updated to {new_status.status_name}',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except EnaRequisitionDetail.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Requisition not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
        except StatusMaster.DoesNotExist:
            return Response({
                'status': 'error',
                'message': f'Status code {status_code} not found in status master'
            }, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



