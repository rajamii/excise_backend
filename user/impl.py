from django.shortcuts import render
from django.views import View
from rest_framework import response, status  
from .models import CustomUser  # Importing the custom user model

# Function to delete a user by their username
def delete_user_by_username(username):
    try:
        # Attempt to get the user with the given username
        user = CustomUser.objects.get(username=username)
        
        # Delete the user from the database
        user.delete()
        print(f"User {username} deleted successfully.")

    except CustomUser.DoesNotExist:
        # Handle case where user with the username doesn't exist
        print(f"User {username} not found.")

    except Exception as e:
        # Handle any other unexpected errors
        print(f"Error deleting user: {e}")

# Function to update a user's details based on their username
def update_user_details(
    username,
    new_mobile_no=None,       # Optional new mobile number
    new_email=None,           # Optional new email
    new_first_name=None,      # Optional new first name
    new_last_name=None,       # Optional new last name
    new_password=None         # Optional new password
):
    try:
        # Retrieve the user with the given username
        user = CustomUser.objects.get(username=username)

        # Update user fields if new values are provided
        if new_mobile_no:
            user.phonenumber = new_mobile_no
        if new_email:
            user.email = new_email
        if new_first_name:
            user.first_name = new_first_name
        if new_last_name:
            user.last_name = new_last_name
        if new_password:
            user.set_password(new_password)  # Use set_password to hash the password properly

        # Save the updated user details to the database
        user.save()
        return True  # Return True to indicate successful update

    except CustomUser.DoesNotExist:
        # If the user doesn't exist, log the message and return False
        print(f"User {username} not found.")
        return False

    except Exception as e:
        # Catch any unexpected errors and return False
        print(f"Error updating user details: {e}")
        return False
