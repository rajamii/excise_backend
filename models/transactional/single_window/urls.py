from django.urls import path
from . import views

urlpatterns = [
    path("search/", views.single_window_search, name="single-window-search"),
    path("latest/", views.single_window_latest_created, name="single-window-latest-created"),
    path("licensee/<int:user_id>/", views.single_window_licensee_detail, name="single-window-licensee-detail"),
    path("application/new/<path:application_id>/", views.single_window_new_app_detail, name="single-window-new-app-detail"),
    path("application/renewal/<path:application_id>/", views.single_window_renewal_app_detail, name="single-window-renewal-app-detail"),
    path("application/salesman-barman/<path:application_id>/", views.single_window_salesman_barman_detail, name="single-window-salesman-barman-detail"),
    path("license/<path:license_id>/", views.single_window_license_detail, name="single-window-license-detail"),

]
