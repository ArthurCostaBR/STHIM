# accounts/admin.py
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("cpf", "username", "sector", "is_active", "created_at")
    list_filter = ("is_active", "sector", "is_staff")
    search_fields = ("cpf", "username")
    ordering = ("is_active", "-created_at")
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("cpf", "password")}),
        ("Dados", {"fields": ("username", "sector")}),
        ("Acesso", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("cpf", "username", "sector", "password1", "password2", "is_active"),
        }),
    )