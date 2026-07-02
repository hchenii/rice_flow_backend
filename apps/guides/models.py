from django.db import models
from apps.farms.models import Farm
from apps.varieties.models import RiceVariety, GrowthStage


class PlantingGuide(models.Model):
    farm        = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='planting_guides')
    variety     = models.ForeignKey(RiceVariety, on_delete=models.CASCADE, related_name='planting_guides')
    season      = models.CharField(max_length=30)
    start_date  = models.DateField()
    # Language the saved steps were generated in — a request in a different
    # language triggers regeneration instead of returning mismatched text.
    language    = models.CharField(max_length=5, default='en')
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Guide: {self.variety.common_name} @ {self.farm.name} ({self.season})"

    class Meta:
        ordering = ['-created_at']


class GuideStep(models.Model):
    guide           = models.ForeignKey(PlantingGuide, on_delete=models.CASCADE, related_name='steps')
    growth_stage    = models.ForeignKey(GrowthStage, on_delete=models.SET_NULL, null=True, blank=True)
    step_no         = models.IntegerField()
    title           = models.CharField(max_length=150)
    description     = models.TextField()
    category        = models.CharField(max_length=20, blank=True, default='')
    days_after_planting = models.IntegerField(null=True, blank=True)
    scheduled_date  = models.DateField(null=True, blank=True)
    is_completed    = models.BooleanField(default=False)
    completed_at    = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Step {self.step_no}: {self.title}"

    class Meta:
        ordering = ['step_no']
        unique_together = ['guide', 'step_no']
