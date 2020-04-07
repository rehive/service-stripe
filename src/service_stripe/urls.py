from django.urls import include, path, re_path
from rest_framework.urlpatterns import format_suffix_patterns

from . import views


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
    re_path(r'^admin/currencies/$', views.AdminListCurrencyView.as_view(), name='admin-currencies-list'),
    re_path(r'^admin/currencies/(?P<code>(\w+))/$', views.AdminCurrencyView.as_view(), name='admin-currencies-view'),
    re_path(r'^admin/payments/$', views.AdminListPaymentView.as_view(), name='admin-payments-list'),
    re_path(r'^admin/payments/(?P<identifier>\w+)/?$', views.AdminPaymentView.as_view(), name='admin-payments-view'),
)

urlpatterns = format_suffix_patterns(urlpatterns)