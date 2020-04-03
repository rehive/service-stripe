import os
import decimal
import stripe
import uuid
from datetime import datetime, date

from rehive import Rehive, APIException
from rest_framework import serializers
from django.db import transaction
from drf_rehive_extras.serializers import BaseModelSerializer
from drf_rehive_extras.fields import TimestampField

from service_stripe.models import Company, User, Currency, Session
from service_stripe.enums import SessionMode

from logging import getLogger


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


class ActivateSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True)
    id = serializers.CharField(source='identifier', read_only=True)
    secret = serializers.UUIDField(read_only=True)
    stripe_api_key = serializers.CharField(read_only=True)
    stripe_publishable_api_key = serializers.CharField(read_only=True)

    def validate(self, validated_data):
        token = validated_data.get('token')
        rehive = Rehive(token)

        try:
            user = rehive.auth.tokens.verify(token)
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

        if Company.objects.filter(
                identifier=company['id'],
                active=True).exists():
            raise serializers.ValidationError(
                {"token": ["Company already activated."]})

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
        # Ceate a new company and activate it.
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
        else:
            company.admin.token = token
            company.active = True
            company.admin.save()
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
            user = rehive.auth.tokens.verify(token)
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
    data = serializers.JSONField()
    type = serializers.CharField()

    def validate(self, validated_data):
        try:
            company = Company.objects.get(
                identifier=self.context.get('view').kwargs.get('company_id')
            )
        except Company.DoesNotExist:
            raise serializers.ValidationError(
                {"non_field_errors": ["Invalid company."]}
            )

        # Initiate stripe variables.
        stripe.api_key = user.company.stripe_api_key
        stripe.api_version = os.environ.get('STRIPE_API_VERSION')
        # Get the signature from the request header.
        sig_header = self.context['request'].META['HTTP_STRIPE_SIGNATURE']

        try:
            event = stripe.Webhook.construct_event(
                payload=self.context['request'].raw_body,
                sig_header=sig_header,
                secret=company.stripe_webhook_secret
            )
        except ValueError as e:
            raise serializers.ValidationError(
                {"non_field_errors": ["Invalid payload."]}
            )
        except stripe.error.SignatureVerificationError as e:
            raise serializers.ValidationError(
                {"non_field_errors": ["Invalid signature"]}
            )

        return validated_data

    def create(self, validated_data):
        # Handle: checkout.session.completed
        if validated_data['type'] == 'checkout.session.completed':
            session = validated_data['data']['object']

            if session['setup_intent']:
                # Retrieve the setup intent
                setup_intent = stripe.SetupIntent.retrieve(
                    session['setup_intent']
                )
                # Attach the payment method to the customer
                stripe.PaymentMethod.attach(
                    setup_intent['payment_method'],
                    customer=setup_intent['metadata']['customer_id'],
                )
                # Set subsrciption to use the payment method by default
                stripe.Subscription.modify(
                    setup_intent['metadata']['subscription_id'],
                    default_payment_method=setup_intent['payment_method']
                )

        return validated_data

# Admin

class AdminCompanySerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier', read_only=True)

    class Meta:
        model = Company
        fields = (
            'id', 'secret', 'stripe_api_key', 'stripe_publishable_api_key',
        )
        read_only_fields = ('id', 'secret',)

# User

class CompanySerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier', read_only=True)

    class Meta:
        model = Company
        fields = ('id', 'stripe_publishable_api_key',)


class SessionSerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier', read_only=True)
    mode = EnumField(enum=SessionMode)

    class Meta:
        model = Session
        fields = ('id', 'mode',)
        read_only_fields = ('id',)

    def validate_mode(self, mode):
        user = self.context['request'].user

        # A setup session must be completed before any other modes an be used.
        if (not user.stripe_customer_id
                and mode != SessionMode.SETUP):
            raise serializers.ValidationError(
                "A setup session needs to be completed before a payment."
            )

        return mode

    def validate(self, validated_data):
        user = self.context['request'].user

        # Ensure the company is configured for Stripe usage.
        if (not user.company.stripe_api_key
                or not user.company.stripe_success_url
                or not user.company.stripe_cancel_url):
            raise serializers.ValidationError(
                {'non_field_errors': ["The company is improperly configured."]}
            )

        return validated_data

    def create(self, validated_data):
        user = self.context['request'].user
        company = user.company
        mode = validated_data.get("mode")

        data = {
            "payment_method_types": ['card'],
            "mode": mode,
            "success_url": company.stripe_success_url \
                + "?session_id={CHECKOUT_SESSION_ID}&succeeded=true",
            "cancel_url": company.stripe_cancel_url \
                + "?session_id: {CHECKOUT_SESSION_ID}&succeeded=false"
        }

        # Add customer data if any already exists.
        if user.stripe_customer_id:
            data["customer"] = user.stripe_customer_id

        # Initiate stripe variables.
        stripe.api_key = user.company.stripe_api_key
        stripe.api_version = os.environ.get('STRIPE_API_VERSION')

        # Call the Stripe SDK to create a session.
        session = stripe.checkout.Session.create(**data)

        # Return the session details.
        return Session.objects.create(
            identifier=session["id"],
            user=user,
            mode=SessionMode.SETUP
        )
