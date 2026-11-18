from django.urls import path
from . import views

app_name = "routes"

urlpatterns = [
    path("", views.route_register_view, name="register"),
    path("<int:pk>/edit/", views.route_register_view, name="edit"),
    path("manage/", views.route_manage_view, name="manage"),
    path("<int:pk>/delete/", views.route_delete_view, name="delete"),
]