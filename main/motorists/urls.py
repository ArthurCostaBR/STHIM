from django.urls import path
from . import views

app_name = "motorists"

urlpatterns = [
    path("", views.motorists_manage_view, name="manage"),
    path("<int:pk>/edit/", views.motorists_manage_view, name="edit"),
    path("<int:pk>/delete/", views.motorists_delete_view, name="delete"),
]