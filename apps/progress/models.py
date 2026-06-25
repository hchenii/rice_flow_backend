from django.db import models
from apps.farms.models import Farm
from apps.varieties.models import RiceVariety, GrowthStage


class FarmCycle(models.Model):
    SEASON_CHOICES = [('wet', 'Wet Season'), ('dry', 'Dry Season')]
    STATUS_CHOICES = [
        ('active',    'Active'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]

    farm           = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='farm_cycles')
    variety        = models.ForeignKey(RiceVariety, on_delete=models.SET_NULL, null=True, blank=True)
    season         = models.CharField(max_length=10, choices=SEASON_CHOICES)
    year           = models.IntegerField()
    planting_date  = models.DateField()
    expected_harvest_date = models.DateField(null=True, blank=True)
    actual_harvest_date   = models.DateField(null=True, blank=True)
    current_stage  = models.ForeignKey(
        GrowthStage, on_delete=models.SET_NULL, null=True, blank=True, related_name='active_cycles'
    )
    status         = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    area_planted_ha = models.FloatField(null=True, blank=True)
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        variety_name = self.variety.common_name if self.variety else 'Unknown'
        return f"{self.farm.name} — {self.get_season_display()} {self.year} ({variety_name})"

    class Meta:
        ordering = ['-planting_date']


class ProgressLog(models.Model):
    ISSUE_CHOICES = [
        ('pest',     'Pest'),
        ('disease',  'Disease'),
        ('weather',  'Weather'),
        ('nutrient', 'Nutrient Deficiency'),
        ('other',    'Other'),
    ]

    farm_cycle    = models.ForeignKey(FarmCycle, on_delete=models.CASCADE, related_name='progress_logs')
    log_date      = models.DateField()
    growth_stage  = models.ForeignKey(GrowthStage, on_delete=models.SET_NULL, null=True, blank=True)
    observation   = models.TextField()
    issue_type    = models.CharField(max_length=15, choices=ISSUE_CHOICES, blank=True)
    action_taken  = models.TextField(blank=True)
    photo_url     = models.URLField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Log {self.log_date} — {self.farm_cycle}"

    class Meta:
        ordering = ['-log_date']


class YieldRecord(models.Model):
    farm_cycle         = models.OneToOneField(FarmCycle, on_delete=models.CASCADE, related_name='yield_record')
    harvest_date       = models.DateField()
    area_harvested_ha  = models.FloatField()
    gross_yield_kg     = models.FloatField()
    net_yield_kg       = models.FloatField()
    moisture_pct       = models.FloatField(default=14.0)
    selling_price_per_kg = models.FloatField(null=True, blank=True)
    gross_income        = models.FloatField(null=True, blank=True)
    production_cost     = models.FloatField(null=True, blank=True)
    net_income          = models.FloatField(null=True, blank=True)
    notes               = models.TextField(blank=True)
    recorded_at         = models.DateTimeField(auto_now_add=True)

    @property
    def yield_per_ha(self):
        if self.area_harvested_ha:
            return round(self.net_yield_kg / self.area_harvested_ha / 1000, 2)
        return None

    def __str__(self):
        return f"Yield: {self.farm_cycle} — {self.net_yield_kg} kg"

    class Meta:
        ordering = ['-harvest_date']
