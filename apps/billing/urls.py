from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path('redeem/', views.RedeemCouponView.as_view(), name='redeem'),
]
