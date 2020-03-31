import os
import decimal
import stripe
from datetime import datetime, date

from rehive import Rehive, APIException
from rest_framework import serializers
from drf_rehive_extras.serializers import BaseModelSerializer
from drf_rehive_extras.fields import TimestampField

from service_stripe.models import Company, User
from service_stripe.enums import SubscriptionStatus

from logging import getLogger


stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
stripe.api_version = os.environ.get('STRIPE_API_VERSION')

logger = getLogger('django')


class AdminCreateCheckoutSessionSerializer(serializers.Serializer):
    # Each list item must contain: '{"plan": ""}'
    items = serializers.ListField(
        child=serializers.JSONField(),
        write_only=True,
        allow_empty=False
    )
    checkout_session = serializers.CharField(read_only=True)

    def validate(self, validated_data):
        """
        Check if an active subscription already exists for a company.
        """

        if Subscription.objects.filter(
                company=self.context['request'].user.company,
                status=SubscriptionStatus.ACTIVE).exists():
            raise serializers.ValidationError(
                {'non_field_errors': [
                    "An active subscription already exists for this company."
                ]}
            )

        return validated_data

    def create(self, validated_data):
        """
        Create the checkout session and the incomplete subscription.
        """

        user = self.context['request'].user
        token = self.context['request'].auth
        items = validated_data.get("items")
        success_url = os.environ.get('SUCCESS_URL')
        cancel_url = os.environ.get('CANCEL_URL')

        # Check if user email is verified
        if not user._email_verified:
            raise serializers.ValidationError(
                {'non_field_errors': [
                    "Please verify your email address before subscribing."
                ]}
            )

        # Create initial subscription data.
        subscription_data = {
            'items': items,
            'metadata': {'company': user.company.identifier}
        }

        # Get the user's company data from Rehive.
        rehive = Rehive(token)
        company_data = rehive.company.get()

        premium = False
        for item in items:
            plan = Plan.objects.get(identifier=item['plan'])
            if plan.slug == 'premium_monthly_us':
                premium = True
                break

        # Calculate remaining trial period and add it to the subscription.
        start_date = datetime.fromtimestamp(company_data['created']/1000)
        current_date = datetime.utcnow()
        days_registered = (current_date - start_date).days
        if days_registered < 14 and not premium:
            trial_period_days = 14 - days_registered
            subscription_data['trial_period_days'] = trial_period_days

        # Create the session data containing the subscription data.
        session_data = {
                "success_url": success_url + "?session_id={CHECKOUT_SESSION_ID}&succeeded=true",
                "cancel_url": cancel_url + "?session_id={CHECKOUT_SESSION_ID}&succeeded=false",
                "payment_method_types": ["card"],
                "mode": "subscription",
                "subscription_data": subscription_data,
                "billing_address_collection": 'required',
        }

        # Check if customer exists in Stripe.
        customer_list = stripe.Customer.list(email=user._email)['data']
        if customer_list:
            # We assume one stripe user per email
            if len(customer_list) > 1:
                logger.exception(
                    "More than one stripe account for {}.".format(user._email)
                )
                raise serializers.ValidationError(
                    {'non_field_errors': [
                        "Error processing your subscription, please contact"
                        " support."
                    ]}
                )
            session_data['customer'] = customer_list[0]['id']
        else:
            # This creates a new stripe user
            session_data['customer_email'] = user._email

        # Customer is only signing up for a subscription.
        checkout_session = stripe.checkout.Session.create(
            **session_data
        )

        # Create a pending subscription in Rehive so that we have a record of
        # it. This has to be marked as active later (on success).
        subscription = Subscription.objects.create(
            user=user,
            company=user.company,
            session_id=checkout_session['id'],
        )
        return {'checkout_session': checkout_session['id']}


class AdminUpdateCheckoutSessionSerializer(serializers.Serializer):
    checkout_session = serializers.CharField(read_only=True)

    def create(self, validated_data):
            try:
                subscription = Subscription.objects.get(
                        company=self.context['request'].user.company,
                        status=SubscriptionStatus.ACTIVE)
            except Subscription.DoesNotExist:
                raise serializers.ValidationError(
                    {'non_field_errors': [
                        "No valid subscription found. Please contact support."
                    ]}
                )

            if not subscription.stripe_id and not subscription.session_id:
                raise serializers.ValidationError(
                    {'non_field_errors': [
                        "Unable to update payment details. Please contact support."
                    ]}
                )

            stripe_subscription = stripe.Subscription.retrieve(
                subscription.stripe_id
            )
            success_url = os.environ.get('SUCCESS_URL')
            cancel_url = os.environ.get('CANCEL_URL')

            checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    mode='setup',
                    setup_intent_data={
                        'metadata': {
                        'customer_id': stripe_subscription['customer'],
                        'subscription_id': stripe_subscription['id'],
                        },
                    },
                    billing_address_collection='required',
                    success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}&succeeded=true",
                    cancel_url=cancel_url + "?session_id={CHECKOUT_SESSION_ID}&succeeded=false",
            )

            return {'checkout_session': checkout_session['id']}


class AdminCompleteCheckoutSessionSerializer(serializers.Serializer):
    checkout_session = serializers.CharField()

    def validate(self, validated_data):
        """
        validate that the the checkout is still relevant and that the related
        subscription is complete.
        """

        session_id = validated_data.get("checkout_session")

        # Ensure that another subscription has not been activated before
        # completing this one.
        if Subscription.objects.filter(
                company=self.context['request'].user.company,
                status=SubscriptionStatus.ACTIVE).exists():
            raise serializers.ValidationError(
                {'non_field_errors': [
                    "An active subscription already exists for this company."
                ]}
            )

        # Find the saved subscription object.
        try:
            subscription = Subscription.objects.get(
                company=self.context['request'].user.company,
                session_id=session_id
            )
        except Subscription.DoesNotExist:
            raise serializers.ValidationError(
                {'checkout_session': [
                    "Checkout session does not exist."
                ]}
            )

        stripe_subscription = stripe.Subscription.retrieve(
            subscription.stripe_id
        )

        if stripe_subscription["status"] not in ("active", "trialing",):
            subscription.status = SubscriptionStatus.FAILED
            subscription.save()
            raise serializers.ValidationError(
                {'checkout_session': [
                    "Checkout was not successfully completed in Stripe."
                ]}
            )

        validated_data["subscription"] = subscription
        return validated_data

    def create(self, validated_data):
        """
        Complete the subscription as it has passed all the validation.
        """

        subscription = validated_data["subscription"]
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.save()
        return {'checkout_session': subscription.session_id}


class AdminSubscriptionSerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier')
    name = serializers.CharField()
    # This field looks for a `_subscription_data` attribute. This should be
    # injected into th einstance before serialization.
    # TODO : possibly consider adding this as a cached model field instead.
    data = serializers.SerializerMethodField()
    created = TimestampField(read_only=True)
    updated = TimestampField(read_only=True)

    class Meta:
        model = Subscription
        fields = ('id', 'name', 'created', 'data', 'updated',)
        read_only_fields = ('id', 'name', 'created', 'data', 'updated',)

    def get_data(self, subscription):
        """
        Get the stripe subscription data.
        """

        if not hasattr(subscription, '_subscription_data'):
            return None

        return subscription._subscription_data


class WebhookSerializer(serializers.Serializer):
    data=serializers.JSONField()
    type=serializers.CharField()

    def validate(self, validated_data):
        webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
        sig_header = self.context['request'].META['HTTP_STRIPE_SIGNATURE']

        try:
            event = stripe.Webhook.construct_event(
                payload=self.context['request'].raw_body, sig_header=sig_header, secret=webhook_secret)
        except ValueError as e:
            logger.exception(e)
            raise serializers.ValidationError(
                    {"Invalid payload"}
                )
        except stripe.error.SignatureVerificationError as e:
            logger.exception(e)
            raise serializers.ValidationError(
                    {"Invalid signature"}
                )

        return validated_data

    def create(self, validated_data):
        if validated_data['type'] == 'checkout.session.completed':
            session = validated_data['data']['object']
            if session['setup_intent']:
                logger.info('Updating customer payment method')
                # Retrieve the setup intent
                setup_intent = stripe.SetupIntent.retrieve(session['setup_intent'])
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
                logger.info('Payment method updated')
        return validated_data
