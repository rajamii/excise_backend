from auth.roles.models import Role
from rest_framework import serializers
from django.core.exceptions import ValidationError

from rest_framework import serializers
from django.core.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied

# serializers.py
class RoleSerializer(serializers.ModelSerializer):
    precedence = serializers.IntegerField(
        source='role_precedence',
        min_value=0,
        max_value=9
    )

    class Meta:
        model = Role
        fields = '__all__'
        # Remove extra_kwargs for 'precedence' — it's now mapped

    def validate_precedence(self, value):
        # Optional: add validation here
        if not (0 <= value <= 9):
            raise ValidationError("Precedence must be between 0 and 9")
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        precedence = attrs.get('role_precedence', self.instance.role_precedence if self.instance else None)

        if self.instance and request:
            current_precedence = self.instance.role_precedence
            new_precedence = attrs.get('role_precedence', current_precedence)

            # Prevent demotion unless high-level admin
            if new_precedence < current_precedence:
                user_role = getattr(request.user, 'role', None)
                if not user_role or user_role.role_precedence < 8:
                    raise ValidationError({
                        'precedence': "Requires admin privileges (level 8+) to demote roles"
                    })
        return attrs

# class RoleSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Role
#         fields = '__all__'
#         extra_kwargs = {
#             'precedence': {'min_value': 0, 'max_value': 9}
#         }

#     def validate(self, attrs):  
#         # ensuring the precedence heirarchy
#         request = self.context.get('request')
        
#         # Instance check for updates
#         if self.instance and request:
#             current_precedence = self.instance.precedence
#             new_precedence = attrs.get('precedence', current_precedence)
            
#             # Precedence demotion check
#             if new_precedence < current_precedence:
#                 # admin here has the precedence of 9
#                 if not hasattr(request.user, 'role') or request.user.role.precedence < 8:
#                     raise ValidationError({
#                         'precedence': "Requires admin privileges to demote roles"
#                     })
        
#         return attrs  
