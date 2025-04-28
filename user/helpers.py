from django.shortcuts import render
from django.views import View
from rest_framework import response, status  
from .models import CustomUser  


'''
 Function to delete a user by their username

'''
def delete_user_by_username(username):

    try:

        # Attempt to get the user with the given username
        # Delete the user from the database
       
        user = CustomUser.objects.get(username=username)
        
        user.delete()
        print(f"User {username} deleted successfully.")


    except CustomUser.DoesNotExist:

        print(f"User {username} not found.")


    except Exception as e:

        print(f"Error deleting user: {e}")



'''
# Function to update a user's details based on their username
    
'''
def update_user_details(
    username,
    new_mobile_no=None,       
    new_email=None,           
    new_first_name=None,      
    new_last_name=None,       
    new_password=None         
):
    try:

        # Retrieve the user with the given username
        # Update user fields if new values are provided
    
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
        return True  

    except CustomUser.DoesNotExist:

        print(f"User {username} not found.")
        return False

    except Exception as e:

        print(f"Error updating user details: {e}")
        return False
