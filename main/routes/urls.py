from django.urls import path
from . import views

app_name = "routes"

urlpatterns = [
    path("", views.route_register_view, name="register"),
    path("selection/", views.route_selection_view, name="selection"),
    path("vehicles/search/", views.vehicle_search_view, name="vehicle_search"),
    path("reset/", views.route_reset_view, name="reset"),
    path("manage/", views.route_manage_view, name="manage"),
    path("<int:pk>/edit/", views.route_edit_view, name="edit"),
    path("<int:pk>/delete/", views.route_delete_view, name="delete"),
]