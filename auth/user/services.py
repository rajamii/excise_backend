from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from auth.user.models import CustomUser, OICOfficerAssignment
from auth.roles.models import Role
from models.transactional.new_license_application.models import NewLicenseApplication
from models.masters.supply_chain.profile.models import UserManufacturingUnit
from models.masters.license.models import License

import string
import secrets


def _split_full_name(full_name: str):
    cleaned = str(full_name or '').strip()
    if not cleaned:
        return 'Officer', 'Incharge'
    parts = cleaned.split(None, 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else 'Officer'
    return first_name, last_name


def _generate_temp_password(length: int = 12):
    if length < 8:
        length = 8
    alphabet = string.ascii_letters + string.digits + '@$!%*?&'
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice('@$!%*?&'),
    ]
    password.extend(secrets.choice(alphabet) for _ in range(length - 4))
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


def _derive_licensee_id(application, license_obj):
    approved_license_id = str(getattr(license_obj, 'license_id', '') or '').strip()
    if approved_license_id:
        return approved_license_id
    source_object_id = str(getattr(license_obj, 'source_object_id', '') or '').strip()
    if source_object_id:
        return source_object_id
    return str(getattr(application, 'application_id', '') or '').strip()


def create_oic_officer_service(payload: dict, created_by_user: CustomUser):
    """
    Service to handle the business logic of creating an OIC officer.
    Raises ValidationError if business rules are violated.
    """
    try:
        application = NewLicenseApplication.objects.get(
            application_id=payload['approved_application_id']
        )
    except NewLicenseApplication.DoesNotExist:
        raise ValidationError("Approved application not found.")

    content_type = ContentType.objects.get_for_model(NewLicenseApplication)
    license_obj = (
        License.objects.filter(
            source_type='new_license_application',
            source_content_type=content_type,
            source_object_id=str(application.application_id),
            is_active=True,
        )
        .order_by('-issue_date')
        .first()
    )
    if not license_obj:
        raise ValidationError("No active license found for selected approved application.")

    oic_role = (
        Role.objects.filter(name__iexact='officer_in_charge').first()
        or Role.objects.filter(id=7).first()
        or Role.objects.filter(name__icontains='officer').first()
    )
    if not oic_role:
        raise ValidationError("Officer In Charge role not configured.")

    first_name, last_name = _split_full_name(payload['name'])
    password = _generate_temp_password()
    address = (
        str(getattr(application, 'business_address', '') or '').strip()
        or str(getattr(application, 'present_address', '') or '').strip()
        or 'N/A'
    )
    licensee_id = _derive_licensee_id(application, license_obj)
    license_type_name = (
        str(getattr(getattr(application, 'license_type', None), 'license_type', '') or '').strip()
        or None
    )

    with transaction.atomic():
        officer = CustomUser.objects.create_user(
            email=payload['email'],
            first_name=first_name,
            middle_name='',
            last_name=last_name,
            phone_number=payload['phone_number'],
            district=application.site_district,
            subdivision=application.site_subdivision,
            address=address,
            password=password,
            role=oic_role,
            created_by=created_by_user,
            is_oic_managed=True,
        )

        assignment = OICOfficerAssignment.objects.create(
            officer=officer,
            approved_application=application,
            license=license_obj,
            licensee_id=licensee_id,
            establishment_name=application.establishment_name,
            created_by=created_by_user,
        )

        UserManufacturingUnit.objects.update_or_create(
            user=officer,
            licensee_id=licensee_id,
            defaults={
                'manufacturing_unit_name': application.establishment_name,
                'license_type': license_type_name,
                'address': address,
            }
        )

    return officer, assignment, password