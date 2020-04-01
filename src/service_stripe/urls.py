from django.urls import include, path, re_path
from rest_framework.urlpatterns import format_suffix_patterns

from . import views

"""
    1. Create a Checkout setup mode Session on your server
    2. Add Checkout to your website
    3. Retrieve the Session object on your server
    4. Retrieve the SetupIntent object on your server
    5. Use the PaymentMethod object on your server
"""

urlpatterns = (
    # Public
    re_path(r'^activate/$', views.ActivateView.as_view(), name='activate'),
    re_path(r'^deactivate/$', views.DeactivateView.as_view(), name='deactivate'),

    # User
    re_path(r'^user/company/$', views.UserCompanyView.as_view(), name='user-company-view'),

    # Admin
    re_path(r'^admin/company/$', views.AdminCompanyView.as_view(), name='admin-company-view'),

    # Admin
    # re_path(r'^admin/checkout-session/$', views.AdminCreateCheckoutSessionView.as_view(), name='admin-create-checkout-session-view'),
    # re_path(r'^admin/update-checkout-session/$', views.AdminUpdateCheckoutSessionView.as_view(), name='admin-update-checkout-session-view'),
    # re_path(r'^admin/complete-checkout-session/?$', views.AdminCompleteCheckoutSessionView.as_view(), name='admin-complete-checkout-session-view'),
    # re_path(r'^admin/checkout-session/(?P<session_id>\w+)/?$', views.AdminCheckoutSessionView.as_view(), name='admin-checkout-session-view'),
    # re_path(r'^admin/payment-methods/(?P<payment_method_id>\w+)/?$', views.AdminPaymentMethodsView.as_view(), name='admin-payment-methods-view'),
    # re_path(r'^admin/subscription/$', views.AdminSubscriptionView.as_view(), name='admin-subscription-view'),
    # re_path(r'^webhook/$', views.WebhookView.as_view(), name='webhook-view'),
)

urlpatterns = format_suffix_patterns(urlpatterns)
