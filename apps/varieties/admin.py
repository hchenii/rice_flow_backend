from django.contrib import admin
from .models import RiceVariety, GrowthStage, FertilizerSchedule, PestDisease


@admin.register(RiceVariety)
class RiceVarietyAdmin(admin.ModelAdmin):
    list_display  = ['variety_id', 'common_name', 'nsic_code', 'ecosystem', 'maturity_days', 'avg_yield_t_ha', 'is_active']
    list_filter   = ['ecosystem', 'is_active', 'drought_tolerance', 'submergence_tolerance']
    search_fields = ['common_name', 'nsic_code', 'variety_id']


@admin.register(GrowthStage)
class GrowthStageAdmin(admin.ModelAdmin):
    list_display = ['stage_no', 'name', 'bbch_min', 'bbch_max', 'days_min_paddy', 'days_max_paddy']
    ordering     = ['stage_no']


@admin.register(FertilizerSchedule)
class FertilizerScheduleAdmin(admin.ModelAdmin):
    list_display = ['app_no', 'stage_name', 'days_after_transplanting', 'fertilizer', 'rate_kg_ha']
    ordering     = ['app_no']


@admin.register(PestDisease)
class PestDiseaseAdmin(admin.ModelAdmin):
    list_display  = ['type', 'common_name', 'scientific_name', 'stage_affected']
    list_filter   = ['type']
    search_fields = ['common_name', 'scientific_name']
    filter_horizontal = ['resistant_varieties']
