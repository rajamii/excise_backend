 # urls.py
from django.urls import path
from .views import (
    user_activity_list,
    track_custom_activity
)

urlpatterns = [
    path('activities/', user_activity_list, name='user-activity-list'),
    path('activities/track/', track_custom_activity, name='track-activity'),
]
