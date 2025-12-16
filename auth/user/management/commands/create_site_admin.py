from django.core.management.base import BaseCommand
from auth.user.models import CustomUser
from auth.roles.models import Role
from models.masters.core.models import District, Subdivision

class Command(BaseCommand):
    help = 'Create a site admin user for frontend login'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Username for site admin')
        parser.add_argument('--email', type=str, help='Email for site admin')
        parser.add_argument('--phone', type=str, help='Phone number for site admin')
        parser.add_argument('--password', type=str, help='Password for site admin')
        parser.add_argument('--first_name', type=str, help='First name')
        parser.add_argument('--last_name', type=str, help='Last name')

    def handle(self, *args, **options):
        username = options.get('username') or 'admin'
        email = options.get('email') or 'admin@excise.gov.in'
        phone = options.get('phone') or '9999999999'
        password = options.get('password') or 'admin123'
        first_name = options.get('first_name') or 'Site'
        last_name = options.get('last_name') or 'Admin'

        # Check if user already exists
        if CustomUser.objects.filter(username=username).exists():
            self.stdout.write(f'User with username "{username}" already exists')
            return

        if CustomUser.objects.filter(email=email).exists():
            self.stdout.write(f'User with email "{email}" already exists')
            return

        if CustomUser.objects.filter(phone_number=phone).exists():
            self.stdout.write(f'User with phone "{phone}" already exists')
            return

        try:
            # Get default district and subdivision
            district = District.objects.first()
            subdivision = Subdivision.objects.first()
            
            if not district or not subdivision:
                self.stdout.write('Error: No district or subdivision found. Please create them first.')
                return

            # Get site_admin role
            try:
                site_admin_role = Role.objects.get(name='site_admin')
            except Role.DoesNotExist:
                self.stdout.write('Error: site_admin role not found. Run setup_roles command first.')
                return

            # Create the user
            user = CustomUser.objects.create_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                phone_number=phone,
                district=district,
                subdivision=subdivision,
                address='Admin Office',
                password=password,
                is_staff=True,
                is_superuser=True,
                is_active=True,
                role=site_admin_role
            )
            
            # Override the auto-generated username
            user.username = username
            user.save()

            self.stdout.write(self.style.SUCCESS(f'Successfully created site admin user:'))
            self.stdout.write(f'Username: {user.username}')
            self.stdout.write(f'Email: {user.email}')
            self.stdout.write(f'Phone: {user.phone_number}')
            self.stdout.write(f'Password: {password}')
            self.stdout.write(f'Role: {user.role.name}')
            self.stdout.write('')
            self.stdout.write('You can now login from the frontend using these credentials.')

        except Exception as e:
            self.stdout.write(f'Error creating user: {str(e)}')