from .models import CustomUser  
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from django.core.cache import cache

def delete_user_by_username(username):

    try:

        user = CustomUser.objects.get(username=username)
        
        user.delete()
        print(f"User {username} deleted successfully.")


    except CustomUser.DoesNotExist:

        print(f"User {username} not found.")


    except Exception as e:

        print(f"Error deleting user: {e}")



def update_user_details(
    username,
    new_mobile_no=None,       
    new_email=None,           
    new_first_name=None,      
    new_last_name=None,       
    new_password=None         
):
    try:
    
        user = CustomUser.objects.get(username=username)

        if new_mobile_no:
            user.phone_number = new_mobile_no
        if new_email:
            user.email = new_email
        if new_first_name:
            user.first_name = new_first_name
        if new_last_name:
            user.last_name = new_last_name
        if new_password:
            user.set_password(new_password)  

        user.save()
        return True  

    except CustomUser.DoesNotExist:

        print(f"User {username} not found.")
        return False

    except Exception as e:

        print(f"Error updating user details: {e}")
        return False


class RedisBlacklistJWTAuthentication(JWTAuthentication):
    def get_validated_token(self, raw_token):
        validated_token = super().get_validated_token(raw_token)
        jti = validated_token.get('jti')
        
        if jti and cache.get(f"blacklisted_token_{jti}"):
            raise InvalidToken("Token has been blacklisted")
            
        return validated_token