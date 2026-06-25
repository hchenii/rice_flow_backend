from django.contrib import admin
from .models import EnvironmentalScan

@admin.register(EnvironmentalScan)
class EnvironmentalScanAdmin(admin.ModelAdmin):
    list_display = ['farm', 'soil_ph', 'avg_temperature', 'annual_rainfall_mm', 'elevation_m', 'flood_risk', 'scanned_at']
    list_filter  = ['flood_risk', 'soil_texture']
