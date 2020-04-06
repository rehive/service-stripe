from django.urls import include, path, re_path
from rest_framework.urlpatterns import format_suffix_patterns

from . import views

"""
    1. CLIENT -> POST /user/sessions/ with a mode of `setup`
        - SERVER creates a session on Stripe
    2. CLIENT -> Use the session_id returned as the redirectToCheckout sessionId
        - CLIENT gets redirected to Stripe setup
    3. SERVER -> Wait for webhooks to indicate the above step was completed
        - SERVER receives webhooks and stores the updated session details
            - checkout.session.completed
            - checkout.session.cancelled?
            - get the `setup_intent`
    4. SERVER -> Store the setup intent object
        - SERVER retrieves a setup intent object
        - Store the payment method
    5. CLIENT -> POST /user/payments/
        SERVER uses the setup intent to create a payment intent (using the payment method)
            -  user confirm=True

    --- START : for 3Dsecure ---

    6. CLIENT -> checks payment status
        -  CLIENT if 3Dsecure is required then redirect again to 3Dsecure facility.

    --- END : for 3Dsecure  ---

    5./7. SERVER -> Wait for webhooks to indicate complete payment
        - SERVER updates payment on service accordingly
    6/8. CLIENT -> pings server for updated status
        - CLIENT displays success/failed/cancel message
"""

urlpatterns = (
    # Public
    re_path(r'^activate/$', views.ActivateView.as_view(), name='activate'),
    re_path(r'^deactivate/$', views.DeactivateView.as_view(), name='deactivate'),
    re_path(r'^webhook/(?P<company_id>\w+)/$', views.WebhookView.as_view(), name='webhook'),

    # User
    re_path(r'^user/company/$', views.UserCompanyView.as_view(), name='user-company-view'),
    re_path(r'^user/sessions/$', views.UserListCreateSessionView.as_view(), name='user-sessions-list'),
    re_path(r'^user/sessions/(?P<identifier>\w+)/?$', views.UserSessionView.as_view(), name='user-sessions-view'),
    re_path(r'^user/payments/$', views.UserListCreatePaymentView.as_view(), name='user-payments-list'),
    re_path(r'^user/payments/(?P<identifier>\w+)/?$', views.UserPaymentView.as_view(), name='user-payments-view'),

    # Admin
    re_path(r'^admin/company/$', views.AdminCompanyView.as_view(), name='admin-company-view'),
)

urlpatterns = format_suffix_patterns(urlpatterns)
