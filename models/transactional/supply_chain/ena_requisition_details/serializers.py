from rest_framework import serializers
from .models import EnaRequisitionDetail
import re


class EnaRequisitionDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnaRequisitionDetail
        fields = '__all__'
        extra_kwargs = {
            'status': {'required': False},
            'status_code': {'required': False},
            'our_ref_no': {'required': False},  # Auto-generated
        }

    def create(self, validated_data):
        from models.masters.supply_chain.status_master.models import StatusMaster
        
        # Auto-generate reference number
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
        validated_data['our_ref_no'] = f"IBPS/{next_number:02d}/EXCISE"
        
        try:
            # Fetch the default status 'RQ_00' (Pending)
            status_obj = StatusMaster.objects.get(status_code='RQ_00')
            validated_data['status_code'] = status_obj.status_code
            validated_data['status'] = status_obj.status_name
        except StatusMaster.DoesNotExist:
            # Fallback or error handling if status master data is missing
            # For now, we'll raise a validation error to alert the issue
            raise serializers.ValidationError("Default status 'RQ_00' not found in StatusMaster.")
            
        return super().create(validated_data)



