from django.urls import include, path, re_path
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions


admin.autodiscover()

schema_view = get_schema_view(
   openapi.Info(
      title="Stripe Service API",
      default_version='v1',
      description="Start by clicking Authorize and adding the header: "
       "Token <your-api-key>. The user endpoints require a normal "
       "rehive user token returned by Rehive's /auth/login/ or "
       "/auth/register/ endpoints."
   ),
   #validators=['flex', 'ssv'],
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    # Administration
    re_path(r'^admin/', admin.site.urls),

    # Swagger
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=None), name='schema-json'),
    re_path(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=None), name='schema-swagger-ui'),
    re_path(r'^$', schema_view.with_ui('redoc', cache_timeout=None), name='schema-redoc'),

    # API
    re_path(r'^api/', include(('service_stripe.urls', 'service_stripe'), namespace='service_stripe')),
]
