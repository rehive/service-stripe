import uuid

from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import smart_text
from rest_framework import authentication, exceptions
from rehive import Rehive, APIException

from .models import Company, User


class HeaderAuthentication(authentication.BaseAuthentication):
    """
    Authentication utility class.
    """

    @staticmethod
    def get_auth_header(request, name="token"):
        try:
            auth = request.META['HTTP_AUTHORIZATION'].split()
        except KeyError:
            return None

        if not auth or smart_text(auth[0].lower()) != name:
            return None

        if not auth[1]:
            return None

        return auth[1]


class AdminAuthentication(HeaderAuthentication):
    """
    Authentication for admin users.
    """

    def authenticate(self, request):
        token = self.get_auth_header(request)
        #token = "" #Overide token for testing

        rehive = Rehive(token)

        try:
            user_data = rehive.auth.tokens.verify(token)
            groups = [g['name'] for g in user_data['groups']]
            if len(set(["admin",]).intersection(groups)) <= 0:
                raise exceptions.AuthenticationFailed(_('Invalid admin user'))
        except APIException as exc:
            if (hasattr(exc, 'data')):
                message = exc.data['message']
            else:
                message = _('Invalid user')

            raise exceptions.AuthenticationFailed(message)

        # NB : This is different from the normal authentication in services.
        # This service does not have to be activated before using it.
        # As such the company is simply created if posisble.
        company, created = Company.objects.get_or_create(
            identifier=user_data['company']
        )

        user, created = User.objects.get_or_create(
            identifier=uuid.UUID(user_data['id']),
            company=company
        )
        # Add temporary extra information to the user data.
        user._email_verified = user_data["verification"]["email"]
        user._email = user_data["email"]

        return user, token


class UserAuthentication(HeaderAuthentication):
    """
    Authentication for users.
    """

    def authenticate(self, request):
        token = self.get_auth_header(request)
        #token = "" #Overide token for testing

        rehive = Rehive(token)

        try:
            user = rehive.auth.tokens.verify(token)
        except APIException as exc:
            if (hasattr(exc, 'data')):
                message = exc.data['message']
            else:
                message = _('Invalid user')

            raise exceptions.AuthenticationFailed(message)

        # NB : This is different from the normal authentication in services.
        # This service does not have to be activated before using it.
        # As such the company is simply created if posisble.
        company, created = Company.objects.get_or_create(
            identifier=user['company']
        )

        user, created = User.objects.get_or_create(
            identifier=uuid.UUID(user['id']),
            company=company
        )
        # Add temporary extra information to the user data.
        user._email_verified = user_data["verification"]["email"]
        user._email = user_data["email"]

        return user, token
