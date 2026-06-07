from django.urls import path

from . import views

app_name = 'affiliates'

urlpatterns = [
    path('', views.AffiliateHubView.as_view(), name='apply'),
    path('dashboard/', views.AffiliateDashboardView.as_view(), name='dashboard'),
    path('thanks/', views.affiliate_success, name='success'),
]
