from django.contrib import admin
from .models import FarmCycle, ProgressLog, YieldRecord


class ProgressLogInline(admin.TabularInline):
    model = ProgressLog
    extra = 0
    fields = ['log_date', 'growth_stage', 'issue_type', 'observation']


class YieldRecordInline(admin.StackedInline):
    model = YieldRecord
    extra = 0


@admin.register(FarmCycle)
class FarmCycleAdmin(admin.ModelAdmin):
    list_display = ['farm', 'variety', 'season', 'year', 'planting_date', 'status']
    list_filter  = ['season', 'status', 'year']
    inlines      = [ProgressLogInline, YieldRecordInline]


@admin.register(ProgressLog)
class ProgressLogAdmin(admin.ModelAdmin):
    list_display = ['farm_cycle', 'log_date', 'issue_type', 'growth_stage']
    list_filter  = ['issue_type']


@admin.register(YieldRecord)
class YieldRecordAdmin(admin.ModelAdmin):
    list_display = ['farm_cycle', 'harvest_date', 'area_harvested_ha', 'net_yield_kg', 'yield_per_ha']
