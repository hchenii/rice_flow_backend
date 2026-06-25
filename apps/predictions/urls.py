from django.urls import path
from .views import ModelComparisonView, TrainModelsView, PredictYieldView

urlpatterns = [
    path('models/',  ModelComparisonView.as_view(), name='prediction-models'),
    path('train/',   TrainModelsView.as_view(),     name='prediction-train'),
    path('predict/', PredictYieldView.as_view(),    name='prediction-predict'),
]
