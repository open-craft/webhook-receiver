from __future__ import unicode_literals

import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from webhook_receiver.utils import receive_json_webhook, hmac_is_valid
from webhook_receiver.utils import fail_and_save, finish_and_save

from .utils import record_order
from .models import Order
from .tasks import process


logger = logging.getLogger(__name__)

FINANCIAL_STATUS_UNENROLL = ["refunded", "voided"]


def extract_webhook_data(func):
    """
    Validate the incoming webhook and extract its content.

    Ensure that the necessary parameters are set on the incoming request. In case the
    data is valid, extract it and pass directly to the wrapped function
    """
    def inner(request):
        # Load configuration
        conf = settings.WEBHOOK_RECEIVER_SETTINGS['shopify']

        try:
            data = receive_json_webhook(request)
        except Exception:
            return HttpResponse(status=400)

        shop_domain = data.headers.get('X-Shopify-Shop-Domain')
        if not shop_domain:
            logger.error('Request is missing X-Shopify-Shop-Domain header')
            fail_and_save(data)
            return HttpResponse(status=400)

        if conf['shop_domain'] != shop_domain:
            logger.error('Unknown shop domain %s' % shop_domain)
            fail_and_save(data)
            return HttpResponse(status=403)

        hmac = data.headers.get('X-Shopify-Hmac-Sha256')
        if not hmac:
            logger.error('Request is missing X-Shopify-Hmac-Sha256 header')
            fail_and_save(data)
            return HttpResponse(status=400)

        if not hmac_is_valid(conf['api_key'], data.body, hmac):
            logger.error('Failed to verify HMAC signature')
            fail_and_save(data)
            return HttpResponse(status=403)

        finish_and_save(data)

        return func(request, conf, data)

    return inner


@csrf_exempt
@require_POST
@extract_webhook_data
def order_create(_, conf, data):
    # Record order creation
    order, created = record_order(data, action=Order.ACTION_ENROLL)
    if created:
        logger.info('Created order %s' % order.order_id)
    else:
        logger.info('Retrieved order %s' % order.order_id)

    send_email = conf.get('send_email', True)

    # Process order
    if order.status == Order.NEW:
        logger.info('Scheduling order %s for processing' % order.order_id)
        process.delay(data.content, Order.ACTION_ENROLL, send_email)
    else:
        logger.info('Order %s already processed, nothing to do' % order.order_id)

    return HttpResponse(status=200)


@csrf_exempt
@require_POST
@extract_webhook_data
def order_delete(_, conf, data):
    # Record order deletion
    order, created = record_order(data, action=Order.ACTION_UNENROLL)
    if created:
        logger.info('Created order %s' % order.order_id)
    else:
        logger.info('Retrieved order %s' % order.order_id)

    send_email = conf.get('send_email', True)

    # Process order
    if order.status == Order.NEW:
        logger.info('Scheduling order %s for processing' % order.order_id)
        process.delay(data.content, Order.ACTION_UNENROLL, send_email)
    else:
        logger.info('Order %s already processed, nothing to do' % order.order_id)

    return HttpResponse(status=200)

@csrf_exempt
@require_POST
@extract_webhook_data
def order_update(_, conf, data):
    payload = data.content
    required_action = Order.ACTION_ENROLL
    if payload['financial_status'] in FINANCIAL_STATUS_UNENROLL:
        required_action = Order.ACTION_UNENROLL

    # Record order updation
    order, created = record_order(data, action=required_action)
    if created:
        logger.info('Created order %s' % order.order_id)
    else:
        logger.info('Retrieved order %s' % order.order_id)

    send_email = conf.get('send_email', True)

    # Process order
    if order.status == Order.NEW:
        logger.info('Scheduling order %s for processing' % order.order_id)
        process.delay(data.content, required_action, send_email)
    else:
        logger.info('Order %s already processed, nothing to do' % order.order_id)

    return HttpResponse(status=200)
