from django.urls import path
from .views import (
    GeneratePlantingGuideView, PlantingGuideListView,
    PlantingGuideDetailView, MarkStepCompleteView, AppendGuideStepView,
)

urlpatterns = [
    path('',                              PlantingGuideListView.as_view(),       name='guide-list'),
    path('<int:pk>/',                     PlantingGuideDetailView.as_view(),     name='guide-detail'),
    path('generate/<int:recommendation_id>/', GeneratePlantingGuideView.as_view(), name='generate-guide'),
    path('append-step/<int:recommendation_id>/', AppendGuideStepView.as_view(),  name='append-guide-step'),
    path('steps/<int:step_id>/complete/', MarkStepCompleteView.as_view(),       name='step-complete'),
]
