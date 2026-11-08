from django.urls import path
from . import views

app_name = "fleet"

urlpatterns = [
    path("", views.vehicle_manage_view, name="manage"),
    path("<int:pk>/edit/", views.vehicle_manage_view, name="edit"),
    path("<int:pk>/delete/", views.vehicle_delete_view, name="delete"),
]