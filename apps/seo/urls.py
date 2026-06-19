from django.urls import path

from .views import SeoLandingView

app_name = 'seo'

urlpatterns = [
    path('<str:section>/', SeoLandingView.as_view(), name='hub'),
    path('<str:section>/<str:slug>/', SeoLandingView.as_view(), name='landing'),
]
