import os
import json
import six
from logging import getLogger
from datetime import datetime, date

import stripe
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.conf import settings
from drf_rehive_extras.generics import *
from rest_framework.parsers import BaseParser, ParseError
from rest_framework.renderers import JSONRenderer
from django.conf import settings

from service_stripe.authentication import *
from service_stripe.serializers import *
from service_stripe.models import *


stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
stripe.api_version = os.environ.get('STRIPE_API_VERSION')

logger = getLogger('django')


"""
Parsers
"""


class RawJSONParser(BaseParser):
    media_type = 'application/json'
    renderer_class = JSONRenderer

    def parse(self, stream, media_type=None, parser_context=None):
        parser_context = parser_context or {}
        encoding = parser_context.get('encoding', settings.DEFAULT_CHARSET)
        request = parser_context.get('request')
        try:
            data = stream.read().decode(encoding)
            # Setting a 'body' alike custom attr with raw POST content.
            setattr(request, 'raw_body', data)
            return json.loads(data)
        except ValueError as exc:
            raise ParseError('JSON parse error - %s' % six.text_type(exc))


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


class WebhookView(CreateAPIView):
    """
    Handle sessions success/cancellation/failure.
    """

    permission_classes = (AllowAny,)
    serializer_class = WebhookSerializer
    parser_classes = (RawJSONParser,)



"""
Admin Endpoints
"""


class AdminCompanyView(RetrieveUpdateAPIView):
    serializer_class = AdminCompanySerializer
    serializer_classes = {
        'PATCH': AdminUpdateCompanySerializer,
        'PUT': AdminUpdateCompanySerializer,
    }
    authentication_classes = (AdminAuthentication,)

    def get_object(self):
        return self.request.user.company

    def update(self, request, *args, **kwargs):
        kwargs['return_serializer'] = self.serializer_class
        return super().update(request, *args, **kwargs)


class AdminListCurrencyView(ListAPIView):
    serializer_class = CurrencySerializer
    authentication_classes = (AdminAuthentication,)
    filter_fields = ('code',)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Currency.objects.none()

        return Currency.objects.filter(
            company=self.request.user.company
        ).order_by('-created')


class AdminCurrencyView(RetrieveAPIView):
    serializer_class = CurrencySerializer
    authentication_classes = (AdminAuthentication,)

    def get_object(self):
        try:
            return Currency.objects.get(
                company=self.request.user.company,
                code__iexact=self.kwargs.get('code')
            )
        except Currency.DoesNotExist:
            raise exceptions.NotFound()


class AdminListPaymentView(ListAPIView):
    serializer_class = AdminPaymentSerializer
    authentication_classes = (UserAuthentication,)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Payment.objects.none()

        return Payment.objects.filter(
            user__company=self.request.user.company
        ).order_by('-created')


class AdminPaymentView(RetrieveAPIView):
    serializer_class = AdminPaymentSerializer
    authentication_classes = (UserAuthentication,)

    def get_object(self):
        try:
            return Payment.objects.get(
                identifier=self.kwargs.get('identifier'),
                user__company=self.request.user.company
            )
        except Payment.DoesNotExist:
            raise exceptions.NotFound()


"""
User Endpoints
"""


class UserCompanyView(RetrieveAPIView):
    serializer_class = CompanySerializer
    authentication_classes = (UserAuthentication,)

    def get_object(self):
        return self.request.user.company


class UserListCreateSessionView(ListCreateAPIView):
    serializer_class = SessionSerializer
    authentication_classes = (UserAuthentication,)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Session.objects.none()

        return Session.objects.filter(
            user=self.request.user
        ).order_by('-created')


class UserSessionView(RetrieveAPIView):
    serializer_class = SessionSerializer
    authentication_classes = (UserAuthentication,)

    def get_object(self):
        try:
            return Session.objects.get(
                identifier=self.kwargs.get('identifier'),
                user=self.request.user
            )
        except Session.DoesNotExist:
            raise exceptions.NotFound()


class UserListCreatePaymentView(ListCreateAPIView):
    serializer_class = PaymentSerializer
    serializer_classes = {
        'POST': CreatePaymentSerializer,
    }
    authentication_classes = (UserAuthentication,)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Payment.objects.none()

        return Payment.objects.filter(
            user=self.request.user
        ).order_by('-created')

    def create(self, request, *args, **kwargs):
        kwargs['return_serializer'] = self.serializer_class
        return super().create(request, *args, **kwargs)


class UserPaymentView(RetrieveAPIView):
    serializer_class = PaymentSerializer
    authentication_classes = (UserAuthentication,)

    def get_object(self):
        try:
            return Payment.objects.get(
                identifier=self.kwargs.get('identifier'),
                user=self.request.user
            )
        except Payment.DoesNotExist:
            raise exceptions.NotFound()
