from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    path("", views.sheets_view, name="sheets"),
    path("patients/", views.patients_report_view, name="patients"),
    path("fleet/", views.fleet_report_view, name="fleet"),
    path("routes/<int:pk>/", views.route_sheet_view, name="route_sheet"),
]