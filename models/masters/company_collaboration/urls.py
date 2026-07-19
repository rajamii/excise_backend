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

    # Liquor Category CRUD
    path('liquor-categories-crud/',                  views.list_categories_crud,      name='liquor-categories-crud-list'),
    path('liquor-categories-crud/create/',           views.create_category_crud,     name='liquor-categories-crud-create'),
    path('liquor-categories-crud/<int:pk>/update/',  views.update_category_crud,     name='liquor-categories-crud-update'),
    path('liquor-categories-crud/<int:pk>/delete/',  views.delete_category_crud,     name='liquor-categories-crud-delete'),

    # Liquor Kind CRUD
    path('liquor-kinds-crud/',                       views.list_kinds_crud,           name='liquor-kinds-crud-list'),
    path('liquor-kinds-crud/create/',                views.create_kind_crud,          name='liquor-kinds-crud-create'),
    path('liquor-kinds-crud/<int:pk>/update/',       views.update_kind_crud,          name='liquor-kinds-crud-update'),
    path('liquor-kinds-crud/<int:pk>/delete/',       views.delete_kind_crud,          name='liquor-kinds-crud-delete'),

    # Liquor Type CRUD
    path('liquor-types-crud/',                       views.list_types_crud,           name='liquor-types-crud-list'),
    path('liquor-types-crud/create/',                views.create_type_crud,          name='liquor-types-crud-create'),
    path('liquor-types-crud/<int:pk>/update/',       views.update_type_crud,          name='liquor-types-crud-update'),
    path('liquor-types-crud/<int:pk>/delete/',       views.delete_type_crud,          name='liquor-types-crud-delete'),

    # Liquor Brand CRUD
    path('liquor-brands-crud/',                      views.list_brands_crud,          name='liquor-brands-crud-list'),
    path('liquor-brands-crud/create/',               views.create_brand_crud,         name='liquor-brands-crud-create'),
    path('liquor-brands-crud/<int:pk>/update/',      views.update_brand_crud,         name='liquor-brands-crud-update'),
    path('liquor-brands-crud/<int:pk>/delete/',      views.delete_brand_crud,         name='liquor-brands-crud-delete'),

    # Brand Pack Sizes (from master_liquor_product)
    # IMPORTANT: <int:size_id> must come BEFORE <path:brand_code> to avoid path capturing "123/delete"
    path('liquor-brands-crud/pack-sizes/<int:size_id>/delete/',   views.delete_brand_pack_size,   name='brand-pack-size-delete'),
    path('liquor-brands-crud/pack-sizes/<path:brand_code>/',      views.brand_pack_sizes_view,    name='brand-pack-sizes'),
]
