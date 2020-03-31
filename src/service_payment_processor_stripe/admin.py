from django.contrib import admin
from service_payment_processor_stripe.models import *

admin.site.register(Company)
admin.site.register(User)
admin.site.register(Subscription)
