from django.db import models
from apps.farms.models import Farm


class EnvironmentalScan(models.Model):
    farm       = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='scans')

    # Soil (from SoilGrids)
    soil_ph            = models.FloatField(null=True, blank=True)
    soil_texture       = models.CharField(max_length=50, blank=True)
    organic_matter     = models.FloatField(null=True, blank=True)
    drainage           = models.CharField(max_length=50, blank=True)
    cec                = models.FloatField(null=True, blank=True)
    nitrogen_ppm       = models.FloatField(null=True, blank=True)
    bulk_density       = models.FloatField(null=True, blank=True)

    # Climate (from Open-Meteo)
    avg_temperature        = models.FloatField(null=True, blank=True)
    temp_at_flowering      = models.FloatField(null=True, blank=True)
    annual_rainfall_mm     = models.FloatField(null=True, blank=True)
    seasonal_rainfall_mm   = models.FloatField(null=True, blank=True)
    humidity_pct           = models.FloatField(null=True, blank=True)
    solar_radiation        = models.FloatField(null=True, blank=True)
    wind_speed_ms          = models.FloatField(null=True, blank=True)
    sunshine_hours         = models.FloatField(null=True, blank=True)

    # Topography (from Open-Meteo Elevation + manual slope)
    elevation_m  = models.FloatField(null=True, blank=True)
    slope_pct    = models.FloatField(null=True, blank=True)

    # Flood/drought risk (derived)
    flood_risk   = models.CharField(max_length=20, blank=True)

    scanned_at   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Scan — {self.farm.name} @ {self.scanned_at.date()}"

    class Meta:
        ordering = ['-scanned_at']
