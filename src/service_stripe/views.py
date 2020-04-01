import os

from logging import getLogger
from datetime import datetime, date

import stripe
from rest_framework.views import APIView
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_rehive_extras.generics import *

from service_stripe.authentication import *
from service_stripe.serializers import *
from service_stripe.models import *
from service_stripe.enums import SubscriptionStatus
from rest_framework.parsers import BaseParser, ParseError
from rest_framework.renderers import JSONRenderer
from django.conf import settings
import json
import six


stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
stripe.api_version = os.environ.get('STRIPE_API_VERSION')

logger = getLogger('django')


"""
Activation Endpoints
"""


class ActivateView(CreateAPIView):
    permission_classes = (AllowAny, )
    serializer_class = ActivateSerializer


class DeactivateView(CreateAPIView):
    permission_classes = (AllowAny, )
    serializer_class = DeactivateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.delete()
        return Response({'status': 'success'})


"""
Admin Endpoints
"""


class AdminCompanyView(RetrieveUpdateAPIView):
    serializer_class = AdminCompanySerializer
    authentication_classes = (AdminAuthentication,)

    def get_object(self):
        return self.request.user.company


"""
User Endpoints
"""


# class UserPublicKeyView(APIView):
#     """
#     Get the public stripe key that can be used on the frontend.
#     """

#     authentication_classes = (AdminAuthentication,)

#     def get(self, request):
#         return Response({"key": os.environ.get('STRIPE_PUBLISHABLE_KEY')})


"""
Admin Endpoints
"""


# class AdminCreateCheckoutSessionView(CreateAPIView):
#     """
#     Instantiate a checkout session to use when checking out via stripe.
#     """

#     serializer_class = AdminCreateCheckoutSessionSerializer
#     authentication_classes = (AdminAuthentication,)


# class RawJSONParser(BaseParser):
#     media_type = 'application/json'
#     renderer_class = JSONRenderer

#     def parse(self, stream, media_type=None, parser_context=None):
#         parser_context = parser_context or {}
#         encoding = parser_context.get('encoding', settings.DEFAULT_CHARSET)
#         request = parser_context.get('request')
#         try:
#             data = stream.read().decode(encoding)
#             setattr(request, 'raw_body', data) # setting a 'body' alike custom attr with raw POST content
#             return json.loads(data)
#         except ValueError as exc:
#             raise ParseError('JSON parse error - %s' % six.text_type(exc))


# class WebhookView(CreateAPIView):
#     """
#     Instantiate a checkout session to use when checking out via stripe.
#     """
#     authentication_classes = []
#     permission_classes = []
#     serializer_class = WebhookSerializer
#     parser_classes = (RawJSONParser,)


# class AdminUpdateCheckoutSessionView(CreateAPIView):
#     """
#     Instantiate a checkout session to use when checking out via stripe.
#     """

#     serializer_class = AdminUpdateCheckoutSessionSerializer
#     authentication_classes = (AdminAuthentication,)


# class AdminCompleteCheckoutSessionView(CreateAPIView):
#     """
#     Complete a checkout session to ensure a checkout was indeed completed.
#     """

#     serializer_class = AdminCompleteCheckoutSessionSerializer
#     authentication_classes = (AdminAuthentication,)


# class AdminCheckoutSessionView(APIView):
#     """
#     View a specific checkout session.
#     """

#     authentication_classes = (AdminAuthentication,)

#     def get(self, request, **kwargs):
#         try:
#             checkout = stripe.checkout.Session.retrieve(
#                 kwargs.get('session_id')
#             )
#         except stripe.error.StripeError as exc:
#             logger.error(exc)
#             raise exceptions.NotFound()

#         return Response(checkout)


# class AdminPaymentMethodsView(APIView):
#     """
#     View a specific checkout session.
#     """

#     authentication_classes = (AdminAuthentication,)

#     def get(self, request, **kwargs):
#         try:
#             checkout = stripe.PaymentMethod.retrieve(
#                 kwargs.get('payment_method_id')
#             )
#         except stripe.error.StripeError as exc:
#             logger.error(exc)
#             raise exceptions.NotFound()

#         return Response(checkout)


# class AdminSubscriptionView(RetrieveAPIView):
#     """
#     Check if there are any active subscriptions on a company.
#     """

#     serializer_class = AdminSubscriptionSerializer
#     authentication_classes = (AdminAuthentication,)

#     def get_object(self):
#         # Retrieve either an active or pending transaction (respectively).
#         # Uses order_by to ensure active statuses are always first.
#         try:
#             subscription = Subscription.objects.filter(
#                 company=self.request.user.company,
#                 status__in=(
#                     SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE,
#                 )
#             ).order_by("status")[0]
#         except IndexError:
#             raise exceptions.NotFound()

#         # Retrieve the subscription from Stripe.
#         # Throw a generic error if anything goes wrong.
#         try:
#             if subscription.stripe_id:
#                 stripe_subscription = stripe.Subscription.retrieve(
#                     subscription.stripe_id
#                 )
#             elif subscription.session_id:
#                 stripe_session = stripe.checkout.Session.retrieve(
#                     subscription.session_id
#                 )
#                 subscription.stripe_id = stripe_session['subscription']
#                 subscription.save()
#                 stripe_subscription = stripe.Subscription.retrieve(
#                     subscription.stripe_id
#                 )

#         except stripe.error.StripeError as exc:
#             logger.error(exc)
#             raise exceptions.NotFound()

#         if subscription.stripe_id:
#             # Sync name:
#             for item in stripe_subscription['items']['data']:
#                 try:
#                     plan = Plan.objects.get(identifier=item['plan']['id'])
#                     if not plan.add_on:
#                         subscription.name = plan.name
#                         break
#                 except Plan.DoesNotExist:
#                     # Don't sync name if plan is not in db
#                     pass

#             # If the retrieved subscription is pending then check if it has
#             # completed since it was last pending.
#             if subscription.status == SubscriptionStatus.PENDING:
#                 # Check if the subscription is not active or trialing.
#                 if stripe_subscription["status"] not in ("active", "trialing", "past_due", "unpaid"):
#                     subscription.status = SubscriptionStatus.FAILED
#                     subscription.save()
#                     raise exceptions.NotFound()
#                 # If it is active/trialing mark the status as active now.
#                 else:
#                     subscription.status = SubscriptionStatus.ACTIVE
#                     subscription.save()

#             # If non-pending subscription is no longer active (or trialing) set it
#             # to expired. This means the subscription was once active but is no
#             # longer active.
#             elif stripe_subscription["status"] not in ("active", "trialing", "past_due", "unpaid"):
#                 subscription.status = SubscriptionStatus.EXPIRED
#                 subscription.save()
#                 raise exceptions.NotFound()

#             # Add the stripe subscription data to the object.
#             subscription._subscription_data = stripe_subscription
#         return subscription

