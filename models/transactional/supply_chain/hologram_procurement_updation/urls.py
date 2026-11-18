from django.urls import path
from .views import (
    list_establishments,
    manual_hologram_entry,
    list_manual_entries,
    get_establishment_wallets,
    credit_establishment_wallet,
    get_establishment_wallet_history,
)

urlpatterns = [
    path('establishments/', list_establishments, name='manual_hologram_establishments'),
    path('save/', manual_hologram_entry, name='manual_hologram_save'),
    path('entries/', list_manual_entries, name='manual_hologram_entries'),
    path('wallets/', get_establishment_wallets, name='manual_establishment_wallets'),
    path('wallets/credit/', credit_establishment_wallet, name='manual_establishment_wallet_credit'),
    path('wallets/history/', get_establishment_wallet_history, name='manual_establishment_wallet_history'),
]
