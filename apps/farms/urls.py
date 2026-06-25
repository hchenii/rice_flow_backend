from django.urls import path
from .views import FarmListCreateView, FarmDetailView, AdminFarmListView, AdminFarmDeleteView, AdminFarmCleanupView

urlpatterns = [
    path('',                FarmListCreateView.as_view(),  name='farm-list'),
    path('all/',            AdminFarmListView.as_view(),   name='admin-farm-list'),
    path('<int:pk>/',       FarmDetailView.as_view(),      name='farm-detail'),
    path('admin/<int:pk>/', AdminFarmDeleteView.as_view(), name='admin-farm-delete'),
    path('cleanup/',        AdminFarmCleanupView.as_view(), name='admin-farm-cleanup'),
]
