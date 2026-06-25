from django.db import models


class RiceVariety(models.Model):
    ECOSYSTEM_CHOICES = [
        ('irrigated_lowland', 'Irrigated Lowland'),
        ('rainfed_lowland',   'Rainfed Lowland'),
        ('upland',            'Upland'),
    ]
    TOLERANCE_CHOICES = [('low', 'Low'), ('moderate', 'Moderate'), ('high', 'High')]

    variety_id          = models.CharField(max_length=20, unique=True)
    nsic_code           = models.CharField(max_length=30)
    common_name         = models.CharField(max_length=100)
    ecosystem           = models.CharField(max_length=30, choices=ECOSYSTEM_CHOICES)
    season              = models.CharField(max_length=30)
    maturity_days       = models.IntegerField()
    avg_yield_t_ha      = models.FloatField()
    max_yield_t_ha      = models.FloatField()
    plant_height_cm     = models.IntegerField(null=True, blank=True)
    grain_type          = models.CharField(max_length=20, blank=True)
    amylose_pct         = models.FloatField(null=True, blank=True)
    submergence_tolerance = models.CharField(max_length=20, choices=TOLERANCE_CHOICES, default='low')
    drought_tolerance     = models.CharField(max_length=20, choices=TOLERANCE_CHOICES, default='low')
    salinity_tolerance    = models.CharField(max_length=20, choices=TOLERANCE_CHOICES, default='low')
    pest_resistance       = models.TextField(blank=True)
    disease_resistance    = models.TextField(blank=True)
    optimal_temp_min      = models.FloatField(default=22)
    optimal_temp_max      = models.FloatField(default=35)
    optimal_rainfall_min  = models.IntegerField(default=1200)
    pagasa_climate_types  = models.CharField(max_length=20, default='IV')
    year_released         = models.IntegerField(null=True, blank=True)
    notes                 = models.TextField(blank=True)
    is_active             = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.common_name} ({self.nsic_code})"

    class Meta:
        verbose_name_plural = 'Rice Varieties'
        ordering = ['variety_id']


class GrowthStage(models.Model):
    stage_no       = models.IntegerField(unique=True)
    bbch_min       = models.IntegerField()
    bbch_max       = models.IntegerField()
    name           = models.CharField(max_length=100)
    days_min_paddy = models.IntegerField()
    days_max_paddy = models.IntegerField()
    days_min_upland= models.IntegerField()
    days_max_upland= models.IntegerField()
    what_to_do     = models.TextField()
    water_management = models.TextField()

    def __str__(self):
        return f"Stage {self.stage_no}: {self.name}"

    class Meta:
        ordering = ['stage_no']


class FertilizerSchedule(models.Model):
    app_no         = models.IntegerField()
    stage_name     = models.CharField(max_length=100)
    days_after_transplanting = models.CharField(max_length=20)
    fertilizer     = models.TextField()
    rate_kg_ha     = models.CharField(max_length=100)
    method         = models.CharField(max_length=100)
    notes          = models.TextField(blank=True)

    def __str__(self):
        return f"App {self.app_no}: {self.stage_name}"

    class Meta:
        ordering = ['app_no']


class PestDisease(models.Model):
    TYPE_CHOICES = [('pest', 'Pest'), ('disease', 'Disease')]

    type            = models.CharField(max_length=10, choices=TYPE_CHOICES)
    common_name     = models.CharField(max_length=100)
    scientific_name = models.CharField(max_length=150, blank=True)
    stage_affected  = models.CharField(max_length=100)
    symptoms        = models.TextField()
    control         = models.TextField()
    resistant_varieties = models.ManyToManyField(RiceVariety, blank=True, related_name='resistant_to')

    def __str__(self):
        return f"{self.get_type_display()}: {self.common_name}"

    class Meta:
        verbose_name_plural = 'Pests & Diseases'
