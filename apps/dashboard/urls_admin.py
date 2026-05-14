from django.urls import path

from . import views

app_name = 'admin_monitor'

urlpatterns = [
    path('', views.SuperuserMonitorView.as_view(), name='dashboard'),
]
