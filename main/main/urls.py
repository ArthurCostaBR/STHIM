from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include("accounts.urls")),
    path('', include("pages.urls")), 
    path('patients/', include("patients.urls")),
    path('fleet/', include("fleet.urls")),
    path('motorists/', include("motorists.urls")),
    path('appoitments/', include("appointments.urls")),
    path('routes/', include("routes.urls")),
    path("reports/", include("reports.urls")),
]