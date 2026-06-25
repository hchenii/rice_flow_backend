from django.urls import path
from .views import ScanFarmView, ScanHistoryView, WeatherForecastView

urlpatterns = [
    path('scan/<int:farm_id>/',    ScanFarmView.as_view(),    name='scan-farm'),
    path('history/<int:farm_id>/', ScanHistoryView.as_view(), name='scan-history'),
    path('weather/',               WeatherForecastView.as_view(), name='weather'),
]
