import uuid
from logging import getLogger

from enumfields import EnumField
from django.db.models import Q
from django.db import models
from django_rehive_extras.models import DateModel

from service_stripe.enums import SessionMode


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
