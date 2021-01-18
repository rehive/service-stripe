import os
import decimal
import uuid
from datetime import datetime, date
from decimal import Decimal

import stripe
from requests.models import PreparedRequest
from rehive import Rehive, APIException
from rest_framework import serializers
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from drf_rehive_extras.serializers import BaseModelSerializer
from drf_rehive_extras.fields import TimestampField

from config import settings
from service_stripe.models import Company, User, Currency, Session, Payment
from service_stripe.enums import SessionMode, PaymentStatus
from service_stripe.utils.common import to_cents, from_cents

from logging import getLogger


stripe.api_version = os.environ.get('STRIPE_API_VERSION')

logger = getLogger('django')


class EnumField(serializers.ChoiceField):
    def __init__(self, enum, **kwargs):
        self.enum = enum
        kwargs['choices'] = [(e.value, e.label) for e in enum]
        super().__init__(**kwargs)

    def to_representation(self, obj):
        try:
            return obj.value
        except AttributeError:
            return obj

    def to_internal_value(self, data):
        try:
            return self.enum(data)
        except ValueError:
            self.fail('invalid_choice', input=data)


class CurrencySerializer(BaseModelSerializer):

    class Meta:
        model = Currency
        fields = (
            'code',
            'display_code',
            'description',
            'symbol',
            'unit',
            'divisibility',
        )


class PaymentMethodCardSerializer(serializers.Serializer):
    brand = serializers.CharField(read_only=True)
    country = serializers.CharField(read_only=True)
    last4 = serializers.CharField(read_only=True)
    exp_month = serializers.IntegerField(read_only=True)
    exp_year = serializers.IntegerField(read_only=True)

    class Meta:
        fields = ('brand', 'country', 'last4', 'exp_month', 'exp_year',)
        read_only_fields = (
            'brand', 'country', 'last4', 'exp_month', 'exp_year',
        )


class PaymentMethodSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    type = serializers.CharField(read_only=True)
    card = PaymentMethodCardSerializer(allow_null=True)

    class Meta:
        fields = ('id', 'type', 'card',)
        read_only_fields = ('id', 'type', 'card',)


class ActivateSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True)
    id = serializers.CharField(source='identifier', read_only=True)
    stripe_api_key = serializers.CharField(read_only=True)
    stripe_publishable_api_key = serializers.CharField(read_only=True)
    stripe_currencies = CurrencySerializer(many=True, read_only=True)

    def validate(self, validated_data):
        token = validated_data.get('token')
        rehive = Rehive(token)

        try:
            user = rehive.auth.get()
            groups = [g['name'] for g in user['groups']]
            if len(set(["admin", "service"]).intersection(groups)) <= 0:
                raise serializers.ValidationError(
                    {"token": ["Invalid admin user."]})
        except APIException:
            raise serializers.ValidationError({"token": ["Invalid user."]})

        try:
            company = rehive.admin.company.get()
        except APIException:
            raise serializers.ValidationError({"token": ["Invalid company."]})

        try:
            currencies = rehive.admin.currencies.get(
                filters={"page_size": 50}
            )
        except APIException:
            raise serializers.ValidationError({"non_field_errors":
                ["Unable to configure currencies."]})

        try:
            subtypes = rehive.admin.subtypes.get()
        except APIException:
            raise serializers.ValidationError(
                {"non_field_errors": ["Unable to configure subtypes."]})

        validated_data['user'] = user
        validated_data['company'] = company
        validated_data['currencies'] = currencies
        validated_data['subtypes'] = subtypes

        return validated_data

    @transaction.atomic
    def create(self, validated_data):
        token = validated_data.get('token')
        rehive_user = validated_data.get('user')
        rehive_company = validated_data.get('company')
        currencies = validated_data.get('currencies')
        subtypes = validated_data.get('subtypes')

        rehive = Rehive(token)

        # Activate an existing company.
        try:
            company = Company.objects.get(
                identifier=rehive_company.get('id')
            )
        # If no company exists create a new new admin user and company.
        except Company.DoesNotExist:
            user = User.objects.create(
                token=token,
                identifier=uuid.UUID(rehive_user['id'])
            )
            company = Company.objects.create(
                admin=user,
                identifier=rehive_company.get('id')
            )
            user.company = company
            user.save()
        # If company existed then reactivate it.
        else:
            # If reactivating a company using a different service admin then
            # create a new user and set it as the admin.
            if str(company.admin.identifier) != rehive_user["id"]:
                user = User.objects.create(
                    token=token,
                    identifier=uuid.UUID(rehive_user['id']),
                    company=company
                )
                # Remove the token from the old admin.
                old_admin = company.admin
                old_admin.token = None
                old_admin.save()
                # Set the new admin.
                company.admin = user
                company.active = True
                company.save()
            # Else just update the admin token with the new one.
            else:
                company.admin.token = token
                company.admin.save()
                company.active = True
                company.save()

        # Add required currencies to service automatically.
        for kwargs in currencies:
            currency = Currency.objects.get_or_create(
                code=kwargs['code'],
                company=company,
                defaults={
                    "display_code": kwargs['display_code'],
                    "description": kwargs['description'],
                    "symbol": kwargs['symbol'],
                    "unit": kwargs['unit'],
                    "divisibility": kwargs['divisibility']
                }
            )

        # Add required subtypes to rehive automatically.
        required_subtypes = [
            {"name": 'deposit_stripe', "tx_type": "credit"},
        ]
        try:
            for rs in required_subtypes:
                if (rs['name'] not in [s['name'] for s in subtypes
                        if s['tx_type'] == rs['tx_type']]):
                    rehive.admin.subtypes.create(
                        name=rs['name'],
                        label=rs['name'].title(),
                        description="{} {} transaction.".format(
                            rs['name'].title(),
                            rs['tx_type']
                        ),
                        tx_type=rs['tx_type']
                    )
        except APIException:
            raise serializers.ValidationError(
                {"non_field_errors": ["Unable to configure subtypes."]})

        return company


class DeactivateSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True)

    def validate(self, validated_data):
        token = validated_data.get('token')
        rehive = Rehive(token)

        try:
            user = rehive.auth.get()
            groups = [g['name'] for g in user['groups']]
            if len(set(["admin", "service"]).intersection(groups)) <= 0:
                raise serializers.ValidationError(
                    {"token": ["Invalid admin user."]})
        except APIException:
            raise serializers.ValidationError({"token": ["Invalid user."]})

        try:
            validated_data['company'] = Company.objects.get(
                identifier=user['company']
            )
        except Company.DoesNotExist:
            raise serializers.ValidationError(
                {"token": ["Inactive company."]})

        return validated_data

    def delete(self):
        company = self.validated_data['company']
        company.active = False
        company.admin.token = None
        company.save()
        company.admin.save()


class WebhookSerializer(serializers.Serializer):
    data = serializers.JSONField(write_only=True)
    type = serializers.CharField(write_only=True)
    message = serializers.CharField(
        allow_null=True, allow_blank=True, required=False, read_only=True
    )

    def validate(self, validated_data):
        try:
            company = Company.objects.get(
                identifier=self.context.get('view').kwargs.get('company_id')
            )
        except Company.DoesNotExist:
            raise serializers.ValidationError(
                {"non_field_errors": ["Invalid company."]}
            )

        if not company.configured:
            raise serializers.ValidationError(
                {'non_field_errors': ["The company is improperly configured."]}
            )

        # Get the signature from the request header.
        sig_header = self.context['request'].META['HTTP_STRIPE_SIGNATURE']

        try:
            event = stripe.Webhook.construct_event(
                payload=self.context['request'].raw_body,
                sig_header=sig_header,
                secret=company.stripe_secret,
                api_key=company.stripe_api_key
            )
        except ValueError as e:
            raise serializers.ValidationError(
                {"non_field_errors": ["Invalid payload."]}
            )
        except stripe.error.SignatureVerificationError as e:
            raise serializers.ValidationError(
                {"non_field_errors": ["Invalid signature"]}
            )

        validated_data["company"] = company
        return validated_data

    def create(self, validated_data):
        company = validated_data.get("company")

        # Handle: checkout.session.completed.
        # When a setup session had been completed.
        if validated_data['type'] == 'checkout.session.completed':
            stripe_session = validated_data['data']['object']
            try:
                # The session must have been initiated via this service and
                # belong to the correct company.
                session = Session.objects.get(
                    identifier=stripe_session["id"], user__company=company
                )
            except Session.DoesNotExist:
                # Do not throw a response error but include a message.
                return {"message": "Invalid session for this service/company."}

            session.completed = True
            session.save()

        # Handle payment_intent.succeeded.
        # When a payment succeeds in Stripe.
        elif validated_data['type'] == 'payment_intent.succeeded':
            intent = validated_data['data']['object']
            try:
                payment = Payment.objects.get(
                    identifier=intent["id"], user__company=company
                )
            except Payment.DoesNotExist:
                # Do not throw a response error but include a message.
                return {"message": "Invalid payment for this service/company."}

            payment.transition(PaymentStatus.SUCCEEDED)

        # Handle payment_intent.payment_failed.
        # When a payment fails in Stripe.
        elif validated_data['type'] == 'payment_intent.payment_failed':
            intent = validated_data['data']['object']
            try:
                payment = Payment.objects.get(
                    identifier=intent["id"], user__company=company
                )
            except Payment.DoesNotExist:
                # Do not throw a response error but include a message.
                return {"message": "Invalid payment for this service/company."}

            error_message = intent['last_payment_error']['message'] \
                if intent.get('last_payment_error') else None

            payment.transition(PaymentStatus.FAILED, error=error_message)

        return validated_data

# Admin

class AdminCompanySerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier', read_only=True)
    stripe_currencies = CurrencySerializer(many=True, read_only=True)

    class Meta:
        model = Company
        fields = (
            'id',
            'stripe_api_key',
            'stripe_publishable_api_key',
            'stripe_currencies',
        )
        read_only_fields = ('id',)


class AdminUpdateCompanySerializer(AdminCompanySerializer):
    id = serializers.CharField(source='identifier', read_only=True)
    stripe_currencies = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        write_only=True,
        max_length=100
    )

    class Meta:
        model = Company
        fields = (
            'id',
            'stripe_api_key',
            'stripe_publishable_api_key',
            'stripe_currencies',

        )
        read_only_fields = ('id',)

    def validate_stripe_currencies(self, currencies):
        return Currency.objects.filter(
            code__in=currencies, company=self.context['request'].user.company
        )

    def validate(self, validated_data):
        user = self.context['request'].user

        # Try and create webhooks if the stripe API key is updated.
        if validated_data.get("stripe_api_key"):
            # Required webhook URL.
            webhook_url = "{}{}/{}/".format(
                getattr(settings, 'BASE_URL'),
                'webhook',
                user.company.identifier
            )
            # New stripe API key to test (and add webhooks).
            stripe_api_key = validated_data["stripe_api_key"]

            try:
                webhooks = stripe.WebhookEndpoint.list(
                    limit=100, api_key=stripe_api_key
                )["data"]
            except stripe.error.StripeError:
                raise serializers.ValidationError(
                    {'stripe_api_key': ["Invalid API key or permissions."]}
                )

            # If no webhook exists matching the webhook requirement, create one.
            matched_webhooks = [w for w in webhooks if w.url == webhook_url]

            if len(matched_webhooks) < 1:
                webhook = stripe.WebhookEndpoint.create(
                    url=webhook_url,
                    enabled_events=[
                        "checkout.session.completed",
                        "payment_intent.succeeded",
                        "payment_intent.payment_failed"
                    ],
                    api_key=stripe_api_key
                )
                # Add the new stripe secret to the validated_data.
                validated_data["stripe_secret"] = webhook["secret"]

        return validated_data

    @transaction.atomic
    def update(self, instance, validated_data):
        stripe_currencies = validated_data.pop("stripe_currencies", None)
        if stripe_currencies:
            instance.stripe_currencies.set(stripe_currencies)

        return super().update(instance, validated_data)


class AdminUserSerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier', read_only=True)

    class Meta:
        model = User
        fields = ('id', 'stripe_customer_id', 'last_payment_method',)
        read_only_fields = (
            'id', 'stripe_customer_id', 'last_payment_method',
        )


class AdminPaymentSerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier', read_only=True)
    user = serializers.CharField(read_only=True)
    status = EnumField(enum=PaymentStatus, read_only=True)
    currency = CurrencySerializer()
    amount = serializers.IntegerField(source="integer_amount")
    created = TimestampField(read_only=True)
    updated = TimestampField(read_only=True)

    class Meta:
        model = Payment
        fields = (
            'id',
            'user',
            'status',
            'error',
            'currency',
            'amount',
            'payment_method',
            'return_url',
            'next_action',
            'collection',
            'created',
            'updated',
        )
        read_only_fields = (
            'id',
            'user',
            'status',
            'error',
            'currency',
            'amount',
            'payment_method',
            'return_url',
            'next_action',
            'collection',
            'created',
            'updated',
        )

# User

class UserSerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier', read_only=True)

    class Meta:
        model = User
        fields = ('id', 'stripe_customer_id', 'last_payment_method',)
        read_only_fields = (
            'id', 'stripe_customer_id', 'last_payment_method',
        )


class CompanySerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier', read_only=True)
    stripe_currencies = CurrencySerializer(many=True, read_only=True)

    class Meta:
        model = Company
        fields = ('id', 'stripe_publishable_api_key', 'stripe_currencies',)


class SessionSerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier', read_only=True)
    mode = EnumField(enum=SessionMode)
    created = TimestampField(read_only=True)
    updated = TimestampField(read_only=True)

    class Meta:
        model = Session
        fields = (
            'id',
            'mode',
            'success_url',
            'cancel_url',
            'completed',
            'created',
            'updated',
        )
        read_only_fields = ('id', 'completed', 'created', 'updated',)

    def validate_mode(self, mode):
        user = self.context['request'].user

        # NOTE : Currently we only support setup sessions.
        if mode != SessionMode.SETUP:
            raise serializers.ValidationError(
                "Only setup sessions are suppported"
            )

        return mode

    def validate_success_url(self, success_url):
        req = PreparedRequest()
        params = {
            "session_id": "{CHECKOUT_SESSION_ID}",
            "succeeded": "true"
        }
        req.prepare_url(success_url, params)
        return req.url

    def validate_cancel_url(self, cancel_url):
        req = PreparedRequest()
        params = {
            "session_id": "{CHECKOUT_SESSION_ID}",
            "succeeded": "false"
        }
        req.prepare_url(cancel_url, params)
        return req.url

    def validate(self, validated_data):
        user = self.context['request'].user

        if not user.company.configured:
            raise serializers.ValidationError(
                {'non_field_errors': ["The company is improperly configured."]}
            )

        # Ensure the user has a customer ID configured in Stripe.
        if not user.stripe_customer_id:
            # Call the Stripe SDK to create a user.
            customer = stripe.Customer.create(
                metadata={"rehive_id": str(user.identifier)},
                api_key=user.company.stripe_api_key
            )
            user.stripe_customer_id = customer["id"]
            user.save()

        return validated_data

    def create(self, validated_data):
        user = self.context['request'].user
        company = user.company
        mode = validated_data.get("mode")
        success_url = validated_data.get("success_url")
        cancel_url = validated_data.get("cancel_url")

        data = {
            "payment_method_types": ['card'],
            "mode": mode.value,
            "customer": user.stripe_customer_id,
            "success_url": success_url,
            "cancel_url": cancel_url
        }

        # Call the Stripe SDK to create a session.
        session = stripe.checkout.Session.create(
            api_key=user.company.stripe_api_key, **data,
        )

        # Return the session details.
        return Session.objects.create(
            identifier=session["id"],
            user=user,
            mode=mode,
            success_url=success_url,
            cancel_url=cancel_url,
            session_data=session
        )


class PaymentSerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier', read_only=True)
    status = EnumField(enum=PaymentStatus, read_only=True)
    currency = CurrencySerializer()
    amount = serializers.IntegerField(source="integer_amount")
    created = TimestampField(read_only=True)
    updated = TimestampField(read_only=True)

    class Meta:
        model = Payment
        fields = (
            'id',
            'status',
            'error',
            'currency',
            'amount',
            'payment_method',
            'return_url',
            'next_action',
            'collection',
            'created',
            'updated',
        )
        read_only_fields = (
            'id',
            'status',
            'error',
            'currency',
            'amount',
            'payment_method',
            'return_url',
            'next_action',
            'collection',
            'created',
            'updated',
        )


class CreatePaymentSerializer(PaymentSerializer):
    currency = serializers.CharField()
    amount = serializers.IntegerField()

    class Meta:
        model = Payment
        fields = (
            'id',
            'status',
            'error',
            'currency',
            'amount',
            'payment_method',
            'return_url',
            'next_action',
            'collection',
            'created',
            'updated',
        )
        read_only_fields = (
            'id',
            'status',
            'error',
            'next_action',
            'collection',
            'created',
            'updated',
        )

    def validate_currency(self, currency):
        user = self.context['request'].user

        try:
            currency = Currency.objects.get(code=currency, company=user.company)
        except Currency.DoesNotExist:
            raise serializers.ValidationError("Invalid currency.")

        if not user.company.stripe_currencies.filter(
                code=currency.code).exists():
            raise serializers.ValidationError("Unsupported currency.")

        return currency

    def validate_payment_method(self, payment_method):
        user = self.context['request'].user

        try:
            user.payment_method(payment_method)
        except ObjectDoesNotExist:
            raise serializers.ValidationError("Invalid payment method.")

        return payment_method

    def validate(self, validated_data):
        user = self.context['request'].user
        currency = validated_data.get("currency")
        amount = validated_data.get("amount")

        if not user.company.configured:
            raise serializers.ValidationError(
                {'non_field_errors': ["The company is improperly configured."]}
            )

        # Format the amount correctly (as a decimal value).
        decimal_amount = from_cents(
            amount=amount,
            divisibility=currency.divisibility
        )

        # Check the size of the decimal number.
        details = decimal_amount.as_tuple()
        if abs(details.exponent) > 18 or len(details.digits) > 30:
            raise serializers.ValidationError(
                {"amount": ["Invalid amount."]}
            )

        validated_data["user"] = user
        # Add the original integer amount in a temporary field.
        validated_data["cent_amount"] = amount
        # Override the original integer amount in the validated data.
        validated_data["amount"] = decimal_amount
        return validated_data

    def create(self, validated_data):
        user = self.context['request'].user
        # Remove this from validated_data as we don't need it on the model.
        cent_amount = validated_data.pop("cent_amount")

        try:
            intent = stripe.PaymentIntent.create(
                amount=cent_amount,
                currency=validated_data["currency"].code.lower(),
                confirm=True,
                customer=user.stripe_customer_id,
                payment_method=validated_data["payment_method"],
                api_key=user.company.stripe_api_key,
                return_url=validated_data["return_url"]
            )
        except stripe.error.CardError as exc:
            raise serializers.ValidationError(
                {'non_field_errors': [exc.error.message]}
            )

        return Payment.objects.create(
            identifier=intent["id"],
            intent_data=intent,
            next_action=intent.get("next_action"),
            **validated_data
        )
