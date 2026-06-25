from django.contrib import admin
from django.contrib import messages
from .models import YieldPredictionModel
from .services import train_all_models


@admin.action(description='Train / Retrain all 3 regression models')
def retrain_models(modeladmin, request, queryset):
    try:
        results = train_all_models()
        YieldPredictionModel.objects.all().delete()
        for r in results:
            YieldPredictionModel.objects.create(**r)
        best = max(results, key=lambda x: x['r2_score'])
        messages.success(
            request,
            f"Models trained. Best: {best['model_type']} "
            f"(R²={best['r2_score']:.4f}, MAE={best['mae']:.4f})"
        )
    except Exception as e:
        messages.error(request, f'Training failed: {e}')


@admin.register(YieldPredictionModel)
class YieldPredictionModelAdmin(admin.ModelAdmin):
    list_display  = ('model_type', 'r2_score', 'mae', 'rmse',
                     'training_samples', 'is_active', 'trained_at')
    list_filter   = ('model_type', 'is_active')
    readonly_fields = ('r2_score', 'mae', 'rmse', 'training_samples',
                       'model_file', 'trained_at')
    actions       = [retrain_models]

    def has_add_permission(self, request):
        return False  # models are created only via training
