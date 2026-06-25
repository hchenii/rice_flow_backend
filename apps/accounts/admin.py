from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display  = ['username', 'email', 'first_name', 'last_name', 'barangay', 'is_active']
    list_filter   = ['is_active', 'barangay']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone']
    fieldsets     = UserAdmin.fieldsets + (
        ('Farm Info', {'fields': ('phone', 'barangay', 'municipality', 'province')}),
    )
