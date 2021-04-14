from __future__ import unicode_literals

import logging

from dateutil.parser import parse as parse_date

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ipware import get_client_ip

from webhook_receiver.utils import receive_json_webhook, hmac_is_valid
from webhook_receiver.utils import fail_and_save, finish_and_save
from .utils import record_order
from .models import WooCommerceOrder as Order
from .tasks import process


logger = logging.getLogger(__name__)


def extract_webhook_data(func):
    """
    Validate the incoming webhook and extract its content.

    Ensure that the necessary parameters are set on the incoming request. In case the
    data is valid, extract it and pass directly to the wrapped function
    """
    def inner(request):
        # Load configuration
        conf = settings.WEBHOOK_RECEIVER_SETTINGS['woocommerce']

        try:
            data = receive_json_webhook(request)
        except Exception:
            return HttpResponse(status=400)

        # When WooCommerce web hooks are first created or enabled,
        # WooCommerce sends a POST request that is not JSON, but instead
        # application/x-www-form-urlencoded with a single form value:
        # "webhook_id=<num>". If we receive that, we return OK
        # immediately. Any other non-JSON content is unexpected, and we
        # send a Bad Request response.
        content_type = request.content_type
        if content_type != 'application/json':
            remote_host, is_routable = get_client_ip(request)
            user_agent = request.headers.get('user-agent')
            if content_type == 'application/x-www-form-urlencoded':
                try:
                    webhook_id = request.POST['webhook_id']
                    logger.info('Webhook with webhook_id %s created or '
                                'enabled from %s (%s)' % (webhook_id,
                                                          remote_host,
                                                          user_agent))
                    return HttpResponse(status=200)
                except KeyError:
                    logger.warn('Received application/x-www-form-urlencoded '
                                'request without a webhook_id parameter '
                                'from %s (%s)' % (remote_host, user_agent))
                    return HttpResponse(status=400)
            else:
                logger.warn('Received request with unexpected '
                            'content type %s '
                            'from %s (%s)' % (content_type,
                                              remote_host,
                                              user_agent))
                return HttpResponse(status=400)

        # Here, we're sure that what we got is JSON, so let's start
        # processing it.
        try:
            data = receive_json_webhook(request)
        except Exception:
            return HttpResponse(status=400)

        source = data.headers.get('X-Wc-Webhook-Source')
        if not source:
            logger.error('Request is missing X-Wc-Webhook-Source header')
            fail_and_save(data)
            return HttpResponse(status=400)

        if conf['source'] != source:
            logger.error('Unknown source %s' % source)
            fail_and_save(data)
            return HttpResponse(status=403)

        hmac = data.headers.get('X-Wc-Webhook-Signature')
        if not hmac:
            logger.error('Request is missing X-Wc-Webhook-Signature header')
            fail_and_save(data)
            return HttpResponse(status=400)

        if not hmac_is_valid(conf['secret'], data.body, hmac):
            logger.error('Failed to verify HMAC signature')
            fail_and_save(data)
            return HttpResponse(status=403)

        finish_and_save(data)

        return func(request, conf, data)

    return inner


@csrf_exempt
@require_POST
@extract_webhook_data
def order_create_or_update(_, conf, data):
    # If we require that an order be paid before we can process it,
    # and it isn't, bail here and wait for the order to be
    # subsequently updated.
    require_payment = conf.get('require_payment', False)
    if require_payment:
        date_paid_gmt = data.content.get('date_paid_gmt')
        if date_paid_gmt:
            try:
                parse_date(date_paid_gmt)
            except ValueError:
                logger.error('Webhook payload %s contains '
                             'invalid value for '
                             'date_paid_gmt: %s' % (data.id,
                                                    date_paid_gmt))
        else:
            logger.warn('Webhook payload %s contains '
                        'empty value for '
                        'date_paid_gmt' % data.id)
            return HttpResponse(status=402)

    # Record order
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
        logger.info('Order %s already processed, '
                    'nothing to do' % order.order_id)

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
