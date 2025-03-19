from django.shortcuts import render
from django.contrib.auth.models import User
from django.views import View
from rest_framework import response , status
# function for registering a user

def registerUser(username , email , password , first_name , last_name ):
    try:

        user = User.objects.create(

             username=username,
             email=email,
             password=password,
             first_name=first_name,
             last_name=last_name,
         )

        user.save()

        return user

    except Exception as e:

        print(f'Error creating user {e}')
        return None


# function for deleting a user by username 

def delete_user_by_username(username):
    try:
        user = User.objects.get(username=username)
        user.delete()
        print(f"User {username} deleted successfully.")
    except User.DoesNotExist:
        print(f"User {username} not found.")
    except Exception as e:
        print(f"Error deleting user: {e}")



# function for updating a user by username  

def update_user_details(

    username,
    new_username=None,
    new_email=None,
    new_first_name=None,
    new_last_name=None,
    new_password=None

):
    try:

        user = User.objects.get(username=username)

        if new_username:
            user.username = new_username
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
        


class UserAPI (View ):

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            
            if User.objects.filter(username=data.get('username')).exists():

                return JsonResponse({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)

            if User.objects.filter(email=data.get('email')).exists():

                return JsonResponse({'error': 'Email already exists'}, status=status.HTTP_400_BAD_REQUEST)

            user = registerUser(
                username    = data.get('username'),
                email       = data.get('email'),
                password    = data.get('password'),
                first_name  = data.get('first_name'),
                last_name   = data.get('last_name'),
            ) 

            
            return JsonResponse({'message': 'User registered successfully'}, status=status.HTTP_201_CREATED)


        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)




    def get(self, request, username=None, *args, **kwargs):
        if username:
            try:
                user = User.objects.get(username=username)
                user_data = {
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                }
                return JsonResponse(user_data, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return JsonResponse({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            users = User.objects.all()
            user_list = [{'username': user.username, 'email': user.email, 'first_name': user.first_name, 'last_name': user.last_name} for user in users]
            return JsonResponse(user_list, safe=False, status=status.HTTP_200_OK)




    def put(self, request, username, *args, **kwargs):
        try:
            data = json.loads(request.body)
            success = update_user_details(
                username,
                new_username=data.get('username'),
                new_email=data.get('email'),
                new_first_name=data.get('first_name'),
                new_last_name=data.get('last_name'),
                new_password=data.get('password'),
            )
            if success:
                return JsonResponse({'message': 'User updated successfully'}, status=status.HTTP_200_OK)
            else:
                return JsonResponse({'error': 'User not found or update failed'}, status=status.HTTP_400_BAD_REQUEST)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)



    def delete(self, request, username, *args, **kwargs):
        try:
            delete_user_by_username(username)
            return JsonResponse({'message': 'User deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
