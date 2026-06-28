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

    # About Us Content APIs
    path('content/create/', views.AboutUsCreateAPIView.as_view(), name='aboutus-create'),
    path('content/list/', views.AboutUsListAPIView.as_view(), name='aboutus-list'),
    path('content/detail/<int:pk>/', views.AboutUsDetailAPIView.as_view(), name='aboutus-detail'),
    path('content/update/<int:pk>/', views.AboutUsUpdateAPIView.as_view(), name='aboutus-update'),
    path('content/delete/<int:pk>/', views.AboutUsDeleteAPIView.as_view(), name='aboutus-delete'),
]
