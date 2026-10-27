from django.urls import path
from .views import (
    list_establishments,
    manual_hologram_entry,
    list_manual_entries,
)

urlpatterns = [
    path('establishments/', list_establishments, name='manual_hologram_establishments'),
    path('save/', manual_hologram_entry, name='manual_hologram_save'),
    path('entries/', list_manual_entries, name='manual_hologram_entries'),
]
