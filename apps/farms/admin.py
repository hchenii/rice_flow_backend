from django.contrib import admin
from .models import Farm

@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display  = ['name', 'user', 'barangay', 'ecosystem', 'area_hectares', 'elevation_m', 'is_active']
    list_filter   = ['ecosystem', 'barangay', 'is_active']
    search_fields = ['name', 'user__username', 'barangay']
