from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/',            include('apps.accounts.urls')),
    path('api/farms/',           include('apps.farms.urls')),
    path('api/environmental/',   include('apps.environmental.urls')),
    path('api/varieties/',       include('apps.varieties.urls')),
    path('api/recommendations/', include('apps.recommendations.urls')),
    path('api/guides/',          include('apps.guides.urls')),
    path('api/progress/',        include('apps.progress.urls')),
    path('api/predictions/',     include('apps.predictions.urls')),
    path('api/ai/',              include('apps.ai.urls')),
    path('api/token/refresh/',   TokenRefreshView.as_view(), name='token_refresh'),
]
