from django.urls import path

from . import views

app_name = 'resell'

urlpatterns = [
    path('product/<slug:slug>/', views.product_detail, name='product_detail'),
    path('', views.store, name='store'),
    path('cart/add/', views.cart_add, name='cart_add'),
    path('cart/remove/', views.cart_remove, name='cart_remove'),
    path('cart/update/', views.cart_update, name='cart_update'),
    path('order/create/', views.create_order, name='create_order'),
    path('order/verify/', views.verify_payment, name='verify_payment'),
]
