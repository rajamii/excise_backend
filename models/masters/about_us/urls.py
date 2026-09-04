from django.urls import path
from . import views

urlpatterns = [
    # Heads of Organisations APIs
    path('headsoforganisations/create/', views.HeadOfOrganisationCreateAPIView.as_view(), name='headsoforganisations-create'),
    path('headsoforganisations/list/', views.HeadOfOrganisationListAPIView.as_view(), name='headsoforganisations-list'),
    path('headsoforganisations/detail/<int:pk>/', views.HeadOfOrganisationDetailAPIView.as_view(), name='headsoforganisations-detail'),
    path('headsoforganisations/update/<int:pk>/', views.HeadOfOrganisationUpdateAPIView.as_view(), name='headsoforganisations-update'),
    path('headsoforganisations/delete/<int:pk>/', views.HeadOfOrganisationDeleteAPIView.as_view(), name='headsoforganisations-delete'),

    # Excise Secretaries / Principal Secretaries APIs
    path('excisesecretaries/create/', views.ExciseSecretaryCreateAPIView.as_view(), name='excisesecretaries-create'),
    path('excisesecretaries/list/', views.ExciseSecretaryListAPIView.as_view(), name='excisesecretaries-list'),
    path('excisesecretaries/detail/<int:pk>/', views.ExciseSecretaryDetailAPIView.as_view(), name='excisesecretaries-detail'),
    path('excisesecretaries/update/<int:pk>/', views.ExciseSecretaryUpdateAPIView.as_view(), name='excisesecretaries-update'),
    path('excisesecretaries/delete/<int:pk>/', views.ExciseSecretaryDeleteAPIView.as_view(), name='excisesecretaries-delete'),

    # Department APIs
    path('department/create/', views.DepartmentCreateAPIView.as_view(), name='department-create'),
    path('department/list/', views.DepartmentListAPIView.as_view(), name='department-list'),
    path('department/detail/<int:pk>/', views.DepartmentDetailAPIView.as_view(), name='department-detail'),
    path('department/update/<int:pk>/', views.DepartmentUpdateAPIView.as_view(), name='department-update'),
    path('department/delete/<int:pk>/', views.DepartmentDeleteAPIView.as_view(), name='department-delete'),

    # Products & Services APIs
    path('products-services/create/', views.ProductsServicesCreateAPIView.as_view(), name='products-services-create'),
    path('products-services/list/', views.ProductsServicesListAPIView.as_view(), name='products-services-list'),
    path('products-services/detail/<int:pk>/', views.ProductsServicesDetailAPIView.as_view(), name='products-services-detail'),
    path('products-services/update/<int:pk>/', views.ProductsServicesUpdateAPIView.as_view(), name='products-services-update'),
    path('products-services/delete/<int:pk>/', views.ProductsServicesDeleteAPIView.as_view(), name='products-services-delete'),

    # Refund & Cancellation Policy APIs
    path('refund-cancellation-policy/create/', views.RefundCancellationPolicyCreateAPIView.as_view(), name='refund-cancellation-policy-create'),
    path('refund-cancellation-policy/list/', views.RefundCancellationPolicyListAPIView.as_view(), name='refund-cancellation-policy-list'),
    path('refund-cancellation-policy/detail/<int:pk>/', views.RefundCancellationPolicyDetailAPIView.as_view(), name='refund-cancellation-policy-detail'),
    path('refund-cancellation-policy/update/<int:pk>/', views.RefundCancellationPolicyUpdateAPIView.as_view(), name='refund-cancellation-policy-update'),
    path('refund-cancellation-policy/delete/<int:pk>/', views.RefundCancellationPolicyDeleteAPIView.as_view(), name='refund-cancellation-policy-delete'),

    # About Us Content APIs (Legacy / General)
    path('content/create/', views.AboutUsCreateAPIView.as_view(), name='aboutus-create'),
    path('content/list/', views.AboutUsListAPIView.as_view(), name='aboutus-list'),
    path('content/detail/<int:pk>/', views.AboutUsDetailAPIView.as_view(), name='aboutus-detail'),
    path('content/update/<int:pk>/', views.AboutUsUpdateAPIView.as_view(), name='aboutus-update'),
    path('content/delete/<int:pk>/', views.AboutUsDeleteAPIView.as_view(), name='aboutus-delete'),
]

