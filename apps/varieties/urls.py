from django.urls import path
from .views import (
    RiceVarietyListView, RiceVarietyDetailView, VarietyImportCSVView,
    GrowthStageListView, FertilizerScheduleListView, PestDiseaseListView,
)

urlpatterns = [
    path('',                      RiceVarietyListView.as_view(),       name='variety-list'),
    path('import-csv/',           VarietyImportCSVView.as_view(),      name='variety-import-csv'),
    path('<int:pk>/',             RiceVarietyDetailView.as_view(),     name='variety-detail'),
    path('growth-stages/',        GrowthStageListView.as_view(),       name='growth-stage-list'),
    path('fertilizer-schedule/', FertilizerScheduleListView.as_view(), name='fertilizer-schedule-list'),
    path('pests-diseases/',       PestDiseaseListView.as_view(),       name='pest-disease-list'),
]
