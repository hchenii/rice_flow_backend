from django.contrib import admin
from django.utils.html import format_html
from .models import ClusterModel, Recommendation, RecommendationResult
from .clustering import train_all_models
from apps.varieties.models import RiceVariety


@admin.register(ClusterModel)
class ClusterModelAdmin(admin.ModelAdmin):
    list_display  = ['name', 'training_time_ms', 'silhouette_score', 'davies_bouldin', 'n_clusters', 'is_active', 'trained_at']
    list_filter   = ['is_active']
    actions       = ['set_as_active', 'train_all']

    def set_as_active(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Select exactly one model to activate.', level='error')
            return
        model = queryset.first()
        model.is_active = True
        model.save()
        self.message_user(request, f'{model.get_name_display()} is now the active model.')
    set_as_active.short_description = '✅ Set as active model'

    def train_all(self, request, queryset):
        varieties = list(RiceVariety.objects.filter(is_active=True))
        results, _ = train_all_models(varieties)
        for name, res in results.items():
            ClusterModel.objects.update_or_create(
                name=name,
                defaults={
                    'training_time_ms': res['training_time_ms'],
                    'silhouette_score': res['silhouette'],
                    'davies_bouldin':   res['davies_bouldin'],
                    'n_clusters':       res['n_clusters'],
                    'is_active':        False,
                }
            )
        self.message_user(request, 'All 3 models trained successfully. Now select the best and set as active.')
    train_all.short_description = '🔁 Train all 3 clustering models'


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ['farm', 'cluster_model', 'created_at']
    list_filter  = ['cluster_model']


@admin.register(RecommendationResult)
class RecommendationResultAdmin(admin.ModelAdmin):
    list_display = ['recommendation', 'rank', 'variety', 'rsi_score', 'suitability_class']
    list_filter  = ['suitability_class']
