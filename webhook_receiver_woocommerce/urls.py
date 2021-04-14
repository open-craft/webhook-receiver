from .views import order_create_or_update, order_delete

from django.urls import path

urlpatterns = [
    path('order/create', order_create_or_update, name='woocommerce_order_create'),
    path('order/update', order_create_or_update, name='woocommerce_order_update'),
    path('order/delete', order_delete, name='woocommerce_order_delete'),
]
