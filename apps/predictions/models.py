from django.db import models


class YieldPredictionModel(models.Model):
    MODEL_CHOICES = [
        ('linear', 'Linear Regression'),
    ]

    model_type       = models.CharField(max_length=20, choices=MODEL_CHOICES)
    r2_score         = models.FloatField(default=0)
    mae              = models.FloatField(default=0, verbose_name='MAE (t/ha)')
    rmse             = models.FloatField(default=0, verbose_name='RMSE (t/ha)')
    training_samples = models.IntegerField(default=0)
    model_file       = models.CharField(max_length=200)
    is_active        = models.BooleanField(default=False)
    trained_at       = models.DateTimeField(auto_now_add=True)
    notes            = models.TextField(blank=True)

    class Meta:
        ordering = ['-trained_at']
        verbose_name = 'Yield Prediction Model'

    def __str__(self):
        return f'{self.get_model_type_display()} — R²={self.r2_score:.3f} ({self.trained_at:%Y-%m-%d})'
