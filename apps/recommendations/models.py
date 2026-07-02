from django.db import models
from django.conf import settings
from apps.farms.models import Farm
from apps.environmental.models import EnvironmentalScan
from apps.varieties.models import RiceVariety


class SuitabilityRuleSet(models.Model):
    """
    Singleton holding the active FAO suitability ranges and WLC weights
    used by the rule-based RSI scoring engine. The admin website edits
    this through GET/PUT /api/recommendations/rules/. The scoring engine
    reads from this row when present; otherwise it falls back to the
    hardcoded defaults in scoring.py.
    """
    payload    = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
    )

    class Meta:
        verbose_name        = 'Suitability rule set'
        verbose_name_plural = 'Suitability rule set'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Suitability rules · last edited {self.updated_at:%Y-%m-%d %H:%M}"


class ClusterModel(models.Model):
    MODEL_CHOICES = [
        ('kmeans', 'K-Means'),
    ]
    name              = models.CharField(max_length=20, choices=MODEL_CHOICES)
    training_time_ms  = models.FloatField()
    silhouette_score  = models.FloatField()
    davies_bouldin    = models.FloatField()
    n_clusters        = models.IntegerField()
    is_active         = models.BooleanField(default=False)
    trained_at        = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.is_active:
            ClusterModel.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_name_display()} — {self.training_time_ms}ms | sil={self.silhouette_score}"

    class Meta:
        ordering = ['-trained_at']


class Recommendation(models.Model):
    farm        = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='recommendations')
    scan        = models.ForeignKey(EnvironmentalScan, on_delete=models.CASCADE)
    cluster_model = models.ForeignKey(ClusterModel, null=True, blank=True, on_delete=models.SET_NULL)
    farm_cluster  = models.IntegerField(default=0)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Recommendation for {self.farm.name} @ {self.created_at.date()}"

    class Meta:
        ordering = ['-created_at']


class RecommendationResult(models.Model):
    recommendation = models.ForeignKey(Recommendation, on_delete=models.CASCADE, related_name='results')
    variety        = models.ForeignKey(RiceVariety, on_delete=models.CASCADE)
    rank           = models.IntegerField()
    rsi_score      = models.FloatField()
    suitability_class = models.CharField(max_length=50)
    variety_cluster   = models.IntegerField(default=0)
    factor_scores     = models.JSONField(default=dict)

    class Meta:
        ordering = ['rank']
