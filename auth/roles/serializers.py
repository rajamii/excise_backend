from auth.roles.models import Role
from rest_framework import serializers
from django.core.exceptions import ValidationError

from rest_framework import serializers
from django.core.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = '__all__'
        extra_kwargs = {
            'precedence': {'min_value': 0, 'max_value': 9}
        }

    def validate(self, attrs):  
        # ensuring the precedence heirarchy
        request = self.context.get('request')
        
        # Instance check for updates
        if self.instance and request:
            current_precedence = self.instance.precedence
            new_precedence = attrs.get('precedence', current_precedence)
            
            # Precedence demotion check
            if new_precedence < current_precedence:
                # admin here has the precedence of 9
                if not hasattr(request.user, 'role') or request.user.role.precedence < 8:
                    raise ValidationError({
                        'precedence': "Requires admin privileges to demote roles"
                    })
        
        return attrs  
