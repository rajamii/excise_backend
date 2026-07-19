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

    # Company details (Original BrandOwner table)
    path('company-details/',                         views.list_company_details,      name='company-details-list'),
    path('company-details/create/',                  views.create_company_detail,     name='company-details-create'),
    path('company-details/<str:brand_owner_code>/',  views.company_detail_detail,     name='company-details-detail'),
    path('company-details/<str:brand_owner_code>/update/', views.update_company_detail, name='company-details-update'),
    path('company-details/<str:brand_owner_code>/delete/', views.delete_company_detail, name='company-details-delete'),

    # Liquor hierarchy
    path('liquor-categories/',                    views.list_liquor_categories, name='liquor-categories'),
    path('liquor-kinds/',                         views.list_liquor_kinds,      name='liquor-kinds'),
    path('liquor-types/',                         views.list_liquor_types,      name='liquor-types'),
    path('liquor-brands/',                        views.list_liquor_brands,     name='liquor-brands'),

    # Fee structure
    path('fee/',                                  views.active_fee,             name='active-fee'),
]
