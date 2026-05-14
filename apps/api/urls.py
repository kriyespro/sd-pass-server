from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'api'

router = DefaultRouter()
router.register('projects', views.ProjectViewSet, basename='project')
router.register('notifications', views.NotificationViewSet, basename='notification')

urlpatterns = [
    path('', views.ApiRootView.as_view(), name='root'),
    path('billing/', views.BillingSummaryView.as_view(), name='billing-summary'),
    path('auth/token/', obtain_auth_token, name='api-token'),
] + router.urls
