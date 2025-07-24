from django.urls import path
from .views import (
    create_transaction,
    list_transactions,
    transaction_detail,
    update_transaction,
    delete_transaction,
    count_transactions
)

urlpatterns = [
    path('create/', create_transaction, name='transaction-create'),
    path('list/', list_transactions, name='transaction-list'),
    path('detail/<int:transaction_id>/', transaction_detail, name='transaction-detail'),
    path('update/<int:transaction_id>/', update_transaction, name='transaction-update'),
    path('delete/<int:transaction_id>/', delete_transaction, name='transaction-delete'),
    path('count/', count_transactions, name='transaction-count'),
]