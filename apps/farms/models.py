from django.db import models
from apps.accounts.models import User


class Farm(models.Model):
    ECOSYSTEM_CHOICES = [
        ('irrigated_lowland', 'Irrigated Lowland'),
        ('rainfed_lowland',   'Rainfed Lowland'),
        ('upland',            'Upland'),
    ]

    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='farms')
    name         = models.CharField(max_length=200)
    barangay     = models.CharField(max_length=100)
    latitude     = models.DecimalField(max_digits=10, decimal_places=7)
    longitude    = models.DecimalField(max_digits=10, decimal_places=7)
    area_hectares= models.DecimalField(max_digits=8, decimal_places=2)
    ecosystem    = models.CharField(max_length=30, choices=ECOSYSTEM_CHOICES, default='irrigated_lowland')
    elevation_m  = models.FloatField(null=True, blank=True)
    slope_pct    = models.FloatField(null=True, blank=True)
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} — {self.user.get_full_name()}"

    class Meta:
        ordering = ['-created_at']
