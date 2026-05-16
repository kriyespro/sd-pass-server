from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.AuthGatewayView.as_view(), {'mode': 'login'}, name='login'),
    path('register/', views.AuthGatewayView.as_view(), {'mode': 'register'}, name='register'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('manual/login/', views.LoginView.as_view(), name='manual_login'),
    path('manual/register/', views.RegisterView.as_view(), name='manual_register'),
    path('', include('allauth.socialaccount.providers.google.urls')),
]
