from django.urls import path
from . import views

app_name = "patients"

urlpatterns = [
    path("", views.patient_manage_view, name="manage"),
    path("<int:pk>/edit/", views.patient_manage_view, name="edit"),
    path("<int:pk>/delete/", views.patient_delete_view, name="delete"),
]