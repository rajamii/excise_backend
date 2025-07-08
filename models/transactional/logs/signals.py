from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out
from .models import UserActivity

User = get_user_model()

@receiver(post_save, sender=User)
def track_registration(sender, instance, created, **kwargs):
    if created:
        UserActivity.objects.create(
            user=instance,
            activity_type=UserActivity.ActivityType.REGISTRATION,
            metadata={
                'registration_method': 'email',  # or 'social', etc.
                'initial_source': kwargs.get('source', 'direct')
            }
        )

@receiver(user_logged_in)
def track_login(sender, request, user, **kwargs):
    UserActivity.objects.create(
        user=user,
        activity_type=UserActivity.ActivityType.LOGIN,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT'),
        metadata={
            'auth_method': kwargs.get('backend', 'email'),
            'session_id': request.session.session_key
        }
    )

@receiver(user_logged_out)
def track_logout(sender, request, user, **kwargs):
    UserActivity.objects.create(
        user=user,
        activity_type=UserActivity.ActivityType.LOGOUT,
        ip_address=get_client_ip(request),
        metadata={
            'session_id': request.session.session_key
        }
    )

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip  
