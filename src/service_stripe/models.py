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
from django.contrib.postgres.fields import ArrayField

from service_stripe.enums import SessionMode, PaymentStatus


logger = getLogger('django')


class Company(DateModel):
    identifier = models.CharField(max_length=100, unique=True, db_index=True)
    admin = models.OneToOneField(
        'service_stripe.User',
        related_name='admin_company',
        on_delete=models.CASCADE
    )
    secret = models.UUIDField()
    stripe_api_key = models.CharField(max_length=100)
    stripe_publishable_api_key = models.CharField(max_length=100)
    stripe_success_url = models.CharField(max_length=150)
    stripe_cancel_url = models.CharField(max_length=150)
    active = models.BooleanField(default=True, blank=False, null=False)

    def __str__(self):
        return self.identifier

    def natural_key(self):
        return (self.identifier,)

    def save(self, *args, **kwargs):
        if not self.id:
            self.secret = uuid.uuid4()

        return super().save(*args, **kwargs)


class User(DateModel):
    identifier = models.UUIDField(unique=True, db_index=True)
    token = models.CharField(max_length=200, null=True)
    company = models.ForeignKey(
        'service_stripe.Company', null=True, on_delete=models.CASCADE
    )
    stripe_customer_id = models.CharField(
        unique=True, db_index=True, max_length=64, null=True
    )
    stripe_payment_method_id = models.CharField(max_length=64, null=True)

    def __str__(self):
        return str(self.identifier)


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

    def __str__(self):
        return str(self.identifier)

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
                    "amount": conversion.integer_to_total_amount,
                    "currency": self.currency.code,
                    "status": "completed",
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



