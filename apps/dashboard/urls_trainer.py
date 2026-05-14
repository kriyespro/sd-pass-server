from django.urls import path

from . import views

app_name = 'trainer'

urlpatterns = [
    path('', views.TrainerOverviewView.as_view(), name='overview'),
    path('audit/env/', views.TrainerEnvAuditListView.as_view(), name='env_audit'),
    path('audit/env/<slug:slug>/', views.TrainerProjectEnvKeysView.as_view(), name='env_audit_project'),
]
