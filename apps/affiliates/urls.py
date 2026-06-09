from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'affiliates'

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='affiliates:partner', permanent=False), name='apply'),
    path('dashboard/', RedirectView.as_view(pattern_name='affiliates:partner', permanent=False), name='dashboard'),
    path('thanks/', RedirectView.as_view(pattern_name='affiliates:partner', permanent=False), name='success'),
    path('partner/', views.PartnerPageView.as_view(), name='partner'),
]
