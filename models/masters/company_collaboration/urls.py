from django.urls import path
from . import views

app_name = 'masters_company_collaboration'

urlpatterns = [
    # Brand owner types
    path('brand-owner-types/',                    views.list_brand_owner_types, name='brand-owner-types'),

    # Brand owners
    path('brand-owners/',                         views.list_brand_owners,      name='brand-owners'),
    path('brand-owners/create/',                  views.create_brand_owner,     name='brand-owner-create'),
    path('brand-owners/<str:brand_owner_code>/',  views.brand_owner_detail,     name='brand-owner-detail'),
    path('brand-owners/<str:brand_owner_code>/update/', views.update_brand_owner, name='brand-owner-update'),
    path('brand-owners/<str:brand_owner_code>/delete/', views.delete_brand_owner, name='brand-owner-delete'),

    # Liquor hierarchy
    path('liquor-categories/',                    views.list_liquor_categories, name='liquor-categories'),
    path('liquor-kinds/',                         views.list_liquor_kinds,      name='liquor-kinds'),
    path('liquor-types/',                         views.list_liquor_types,      name='liquor-types'),
    path('liquor-brands/',                        views.list_liquor_brands,     name='liquor-brands'),

    # Fee structure
    path('fee/',                                  views.active_fee,             name='active-fee'),
]
