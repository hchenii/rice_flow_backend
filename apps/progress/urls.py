from django.urls import path
from .views import (
    FarmCycleListCreateView, FarmCycleDetailView,
    ProgressLogListCreateView, ProgressLogDetailView,
    YieldRecordView,
    AdminFarmCycleListView, AdminFarmCycleDetailView,
)

urlpatterns = [
    path('cycles/',                       FarmCycleListCreateView.as_view(),   name='cycle-list'),
    path('cycles/<int:pk>/',              FarmCycleDetailView.as_view(),       name='cycle-detail'),
    path('logs/',                         ProgressLogListCreateView.as_view(), name='log-list'),
    path('logs/<int:pk>/',                ProgressLogDetailView.as_view(),     name='log-detail'),
    path('cycles/<int:cycle_id>/yield/',  YieldRecordView.as_view(),           name='yield-record'),

    path('admin/cycles/',                 AdminFarmCycleListView.as_view(),    name='admin-cycle-list'),
    path('admin/cycles/<int:pk>/',        AdminFarmCycleDetailView.as_view(),  name='admin-cycle-detail'),
]
