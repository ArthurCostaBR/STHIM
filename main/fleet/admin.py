from django.contrib import admin
from .models import Vehicle
from .forms import VehicleForm

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    form = VehicleForm
    list_display = ("plate", "vehicle_type", "seats", "is_operational")
    search_fields = ("plate",)
    list_filter = ("vehicle_type", "is_operational")
