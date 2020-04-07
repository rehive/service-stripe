import uuid
from logging import getLogger
from decimal import Decimal

import stripe
from enumfields import EnumField
from rehive import Rehive, APIException
from django.db.models import Q
from django.db import models, transaction
from django_rehive_extras.models import DateModel
from django_rehive_extras.fields import MoneyField
from django.contrib.postgres.fields import ArrayField, JSONField

from service_stripe.utils.common import to_cents
from service_stripe.enums import SessionMode, PaymentStatus


logger = getLogger('django')


class Company(DateModel):
    identifier = models.CharField(max_length=100, unique=True, db_index=True)
    admin = models.OneToOneField(
        'service_stripe.User',
        related_name='admin_company',
        on_delete=models.CASCADE
    )
    # Stripe API keys and secrets.
    stripe_api_key = models.CharField(max_length=100, null=True)
    stripe_secret = models.CharField(max_length=150, null=True)
    stripe_publishable_api_key = models.CharField(max_length=100, null=True)
    # Setup session URLs.
    stripe_success_url = models.CharField(max_length=150, null=True)
    stripe_cancel_url = models.CharField(max_length=150, null=True)
    # Payment intent return URL.
    stripe_return_url = models.CharField(max_length=150, null=True)
    # List of currencies supported for Stripe payments.
    stripe_currencies = models.ManyToManyField(
        'service_stripe.Currency', related_name="+"
    )
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.identifier

    def natural_key(self):
        return (self.identifier,)

    @property
    def configured(self):
        if (self.stripe_api_key
                and self.stripe_secret
                and self.stripe_publishable_api_key
                and self.stripe_success_url
                and self.stripe_cancel_url
                and self.stripe_return_url
                and self.active):
            return True

        return False


class User(DateModel):
    identifier = models.UUIDField(unique=True, db_index=True)
    token = models.CharField(max_length=200, null=True)
    company = models.ForeignKey(
        'service_stripe.Company', null=True, on_delete=models.CASCADE,
    )
    stripe_customer_id = models.CharField(
        unique=True, db_index=True, max_length=64, null=True
    )
    stripe_payment_method_id = models.CharField(max_length=64, null=True)

    def __str__(self):
        return str(self.identifier)

    @property
    def configured(self):
        if (self.stripe_cutsomer_id
                and self.stripe_payment_method_id):
            return True

        return False


class Currency(DateModel):
    company = models.ForeignKey(
        'service_stripe.Company', on_delete=models.CASCADE
    )
    code = models.CharField(max_length=30, db_index=True)
    display_code = models.CharField(max_length=12, null=True, blank=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    symbol = models.CharField(max_length=30, null=True, blank=True)
    unit = models.CharField(max_length=30, null=True, blank=True)
    divisibility = models.IntegerField(default=2)
    enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = ('company', 'code')

    def __str__(self):
        return str(self.code)


class Session(DateModel):
    identifier = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey('service_stripe.User', on_delete=models.CASCADE)
    mode = EnumField(SessionMode, max_length=20, db_index=True)
    completed = models.BooleanField(default=False)
    # NOTE: Internal-only Stripe data, should not be accessible via the API.
    # This is a point in time snapshot taken at the time of creation.
    session_data = JSONField(null=True, blank=True)

    def __str__(self):
        return str(self.identifier)


class Payment(DateModel):
    identifier = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey('service_stripe.User', on_delete=models.CASCADE)
    currency = models.ForeignKey(
        'service_stripe.Currency', on_delete=models.CASCADE
    )
    amount = MoneyField(default=Decimal(0))
    status = EnumField(
        PaymentStatus,
        max_length=24,
        default=PaymentStatus.PROCESSING,
        db_index=True
    )
    error = models.CharField(max_length=250, null=True)
    collection = models.CharField(max_length=64, null=True)
    txns = ArrayField(
        models.CharField(max_length=64, blank=True),
        default=list
    )
    # NOTE: Internal-only Stripe data, should not be accessible via the API.
    # This is a point in time snapshot taken at the time of creation.
    intent_data = JSONField(null=True, blank=True)
    next_action = JSONField(null=True, blank=True)

    def __str__(self):
        return str(self.identifier)

    def save(self, *args, **kwargs):
        """
        Unset the "next action" field when the status is updated to anything
        besides processing.
        """
        if self.status in  (PaymentStatus.SUCCEEDED, PaymentStatus.FAILED,):
            self.next_action = None

        return super().save(*args, **kwargs)

    @property
    def integer_amount(self):
        """
        Get an integer from amount.
        """

        divisibility = Decimal(self.currency.divisibility)
        return to_cents(self.amount, divisibility)

    @transaction.atomic
    def transition(self, status, error=None):
        # Ensure that failed or succeeded payments aren't transitioned.
        # NOTE: this will be removed once we add this functionality.
        if self.status in (PaymentStatus.FAILED, PaymentStatus.SUCCEEDED,):
            raise ValueError("Cannot change the payment status.")

        # Handle failed payments.
        if status == PaymentStatus.FAILED:
            self.status = status
            self.error = errror

        # Handle succeeded payments.
        elif status == PaymentStatus.SUCCEEDED:
            self.status = status
            transactions = [
                {
                    "user": self.user.identifier,
                    "amount": self.integer_amount,
                    "currency": self.currency.code,
                    "status": "completed",
                    "subtype": "deposit_stripe",
                    "tx_type": "credit",
                }
            ]

            rehive = Rehive(self.user.company.admin.token)
            collection = rehive.admin.transaction_collections.post(
                transactions=transactions
            )
            self.collection = collection["id"]
            self.txns = [
                txn['id'] for txn in collection["transactions"]
            ]

        # Self the payment with its new data.
        self.save()