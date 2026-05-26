from django.urls import path

from . import views

app_name = 'affiliates'

urlpatterns = [
    path('', views.AffiliateApplyView.as_view(), name='apply'),
    path('thanks/', views.affiliate_success, name='success'),
]
