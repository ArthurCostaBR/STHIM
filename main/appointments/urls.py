from django.urls import path
from . import views

app_name = "appointments"

urlpatterns = [
    path("", views.appointment_schedule_view, name="schedule"),
    path("<int:pk>/edit/", views.appointment_schedule_view, name="edit"),
    path("manage/", views.appointment_manage_view, name="manage"),
    path("<int:pk>/delete/", views.appointment_delete_view, name="delete"),
    path("patients/search/", views.patient_search_view, name="patient_search"),
]