from django.urls import path

from . import views

app_name = 'ops'

urlpatterns = [
    path('', views.StaffPlatformOverviewView.as_view(), name='overview'),
]
