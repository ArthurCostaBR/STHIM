from django.contrib import admin
from .forms import MotoristsForm
from .models import Motorists

@admin.register(Motorists)
class DriverAdmin(admin.ModelAdmin):
    form = MotoristsForm
    list_display = ("name", "cpf", "phone")
    search_fields = ("name", "cpf")