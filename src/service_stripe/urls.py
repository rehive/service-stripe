from django.urls import include, path, re_path
from rest_framework.urlpatterns import format_suffix_patterns

from . import views


urlpatterns = (
    # Public
    re_path(r'^activate/$', views.ActivateView.as_view(), name='activate'),
    re_path(r'^deactivate/$', views.DeactivateView.as_view(), name='deactivate'),

    # Admin
    re_path(r'^admin/company/$', views.AdminCompanyView.as_view(), name='admin-company'),

	# User
	# re_path(r'^user/public-key/$', views.UserPublicKeyView.as_view(), name='user-public-key-view'),

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
