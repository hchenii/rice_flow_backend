from django.urls import path
from .views import (
    RegisterView, LoginView, ProfileView,
    AdminUserListView, AdminUserDetailView, AdminStatsView, SystemHealthView,
)

urlpatterns = [
    path('register/',     RegisterView.as_view(),       name='register'),
    path('login/',        LoginView.as_view(),           name='login'),
    path('profile/',      ProfileView.as_view(),         name='profile'),
    path('users/',        AdminUserListView.as_view(),   name='admin-users'),
    path('users/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('admin-stats/',  AdminStatsView.as_view(),      name='admin-stats'),
    path('system-health/', SystemHealthView.as_view(),   name='system-health'),
]
