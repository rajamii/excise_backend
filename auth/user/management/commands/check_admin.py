from django.core.management.base import BaseCommand
from auth.user.models import CustomUser
from auth.roles.models import Role

class Command(BaseCommand):
    help = 'Check admin user details'

    def handle(self, *args, **options):
        try:
            user = CustomUser.objects.get(is_superuser=True)
            self.stdout.write(f'Username: {user.username}')
            self.stdout.write(f'Email: {user.email}')
            self.stdout.write(f'Phone: {user.phone_number}')
            self.stdout.write(f'First Name: {user.first_name}')
            self.stdout.write(f'Last Name: {user.last_name}')
            self.stdout.write(f'Role: {user.role.name if user.role else "No role"}')
            self.stdout.write(f'Is Staff: {user.is_staff}')
            self.stdout.write(f'Is Superuser: {user.is_superuser}')
            self.stdout.write(f'Is Active: {user.is_active}')
            
            # Check if site_admin role exists
            try:
                site_admin_role = Role.objects.get(name='site_admin')
                self.stdout.write(f'Site Admin Role exists: {site_admin_role.name} (precedence: {site_admin_role.role_precedence})')
            except Role.DoesNotExist:
                self.stdout.write('Site Admin Role does NOT exist')
                
        except CustomUser.DoesNotExist:
            self.stdout.write('No superuser found')