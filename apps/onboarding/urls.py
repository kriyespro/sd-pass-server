from django.urls import path

from . import views

app_name = 'onboarding'

urlpatterns = [
    path('', views.OnboardingWizardPartialView.as_view(), name='wizard'),
    path('step/<int:step>/', views.OnboardingStepView.as_view(), name='step'),
    path('skip/', views.OnboardingSkipView.as_view(), name='skip'),
]
