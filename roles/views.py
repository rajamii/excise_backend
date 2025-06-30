from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import HttpRequest
from roles.models import Role

def is_dev(request: HttpRequest):
    if request.user.role.name == 'dev':
        return True
    return False


ACCESS_ATTRIBUTE_MAP = {
    'user': 'user_access',
    'company_registration': 'company_registration_access',
    'contact_us': 'contact_us_access',
    'license_application': 'license_application_access',
    'masters': 'masters_access',
    'roles': 'roles_access',
    'salesman_barman': 'salesman_barman_registration_access',
}


def is_role_capable_of(request: HttpRequest, operation, model):
    if model in ACCESS_ATTRIBUTE_MAP:

        # Get the model from the map
        access_attribute = ACCESS_ATTRIBUTE_MAP[model]

        # Get the role from the request
        role = getattr(request.user, 'role', None)

        if not role:
            return False

        # check to see if the accesss level
        # is above or equal to the  level of role

        access_level = getattr(role, access_attribute, None)
        return access_level in [Role.READ_WRITE, operation]  # cleaner

    return False  # Handle cases where the model is not in the map

@api_view(['GET'])
def role_list(request):
    roles = Role.objects.all().values('id', 'name')
    return Response(list(roles), status=200)
