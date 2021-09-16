from .views import order_create, order_delete, order_update

from django.urls import path

urlpatterns = [
    path('order/create', order_create, name='shopify_order_create'),
    path('order/delete', order_delete, name='shopify_order_delete'),
    path('order/update', order_update, name='shopify_order_update'),
]
