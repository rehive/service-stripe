import uuid
from logging import getLogger

from enumfields import EnumField
from django.db.models import Q
from django.db import models
from django_rehive_extras.models import DateModel

from service_payment_processor_stripe.enums import SubscriptionStatus


logger = getLogger('django')


class Company(DateModel):
    identifier = models.CharField(max_length=100, unique=True, db_index=True)

    def __str__(self):
        return self.identifier

    def natural_key(self):
        return (self.identifier,)


class User(DateModel):
    identifier = models.UUIDField(unique=True, db_index=True)
    company = models.ForeignKey(
        'service_payment_processor_stripe.Company', on_delete=models.CASCADE
    )

    def __str__(self):
        return str(self.identifier)
