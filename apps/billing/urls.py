from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path('redeem/', views.RedeemCouponView.as_view(), name='redeem'),
    path('create-order/', views.create_order, name='create_order'),
    path('verify-payment/', views.verify_payment, name='verify_payment'),
]
