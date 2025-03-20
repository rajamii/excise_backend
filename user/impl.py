
from django.shortcuts import render
from django.views import View
from rest_framework import response , status
from .models import CustomUser

# genereate new username 


# function for registering a user

def registerUser(username , email , password , first_name , last_name , mobile_no ):
    try:

        user = CustomUser.objects.create_user(

            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phonenumber=mobile_no,
         )

        user.save()

        return user

    except Exception as e:

        print(f'Error creating user {e}')
        return None


# function for deleting a user by username 

def delete_user_by_username(username):
    try:
        user = CustomUser.objects.get(username=username)
        user.delete()
        print(f"User {username} deleted successfully.")
    except User.DoesNotExist:
        print(f"User {username} not found.")
    except Exception as e:
        print(f"Error deleting user: {e}")



# function for updating a user by username  

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
            user.phonenumber = new_mobile_no
        if new_email:
            user.email = new_email
        if new_first_name:
            user.first_name = new_first_name
        if new_last_name:
            user.last_name = new_last_name
        if new_password:
            user.set_password(new_password)

        user.save()
        return True #Return True for Success.

    except User.DoesNotExist:

        print(f"User {username} not found.")
        return False

    except Exception as e:

        print(f"Error updating user details: {e}")
        return False 
        



