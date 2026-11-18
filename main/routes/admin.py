from django.contrib import admin
from .models import TransportRecord


@admin.register(TransportRecord)
class TransportRecordAdmin(admin.ModelAdmin):
    list_display = (
        "route_date", "departure_time", "region", "vehicle_plate",
        "motorist_name", "name", "is_companion",
    )
    list_filter = ("route_date", "region", "is_companion")
    search_fields = ("name", "vehicle_plate", "motorist_name")
    readonly_fields = [field.name for field in TransportRecord._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser