from django.contrib import admin
from .models import PlantingGuide, GuideStep


class GuideStepInline(admin.TabularInline):
    model = GuideStep
    extra = 0
    fields = ['step_no', 'title', 'scheduled_date', 'is_completed', 'completed_at']
    readonly_fields = ['completed_at']


@admin.register(PlantingGuide)
class PlantingGuideAdmin(admin.ModelAdmin):
    list_display = ['farm', 'variety', 'season', 'start_date', 'created_at']
    list_filter  = ['season']
    inlines      = [GuideStepInline]


@admin.register(GuideStep)
class GuideStepAdmin(admin.ModelAdmin):
    list_display = ['guide', 'step_no', 'title', 'scheduled_date', 'is_completed']
    list_filter  = ['is_completed']
