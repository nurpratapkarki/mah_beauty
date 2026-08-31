from django.http import HttpResponseBadRequest
from django.utils.translation import gettext_lazy as _

from allauth.account.utils import filter_users_by_email
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import EmailAddress, SocialAccount


from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.utils.translation import gettext_lazy as _

from allauth.account.utils import filter_users_by_email
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import EmailAddress, SocialAccount

from accounts.models import User


def _email_owner_pks(email):
    """Users owning ``email`` (verified via an EmailAddress row OR their own
    ``User.email``), case-insensitively.
    """
    owner_pks = EmailAddress.objects.filter(
        email__iexact=email,
    ).values_list('user_id', flat=True)
    return set(owner_pks) | set(
        User.objects.filter(email__iexact=email).values_list('pk', flat=True),
    )


class MahBeautySocialAccountAdapter(DefaultSocialAccountAdapter):
    """FR-008 email-merge policy for social (Google) logins.

    - Google email already on a password account  -> auto-connect (second path,
      controlled by `SOCIALACCOUNT_EMAIL_AUTHENTICATION`/`_AUTO_CONNECT`).
    - Google email already owned by a *different* Google identity -> reject 400.
    - Unverified Google email colliding with an existing account, or an account
      that is inactive, -> reject 400 (never silently merged).
    - The matched account must be active (inactive accounts are never merged).
    """

    def authenticate_by_email(self, sociallogin):
        from allauth.socialaccount.app_settings import EMAIL_AUTHENTICATION_AUTO_CONNECT

        emails = [e.email for e in sociallogin.email_addresses if e.verified]
        for email in emails:
            if not self.can_authenticate_by_email(sociallogin, email):
                continue
            users = [
                user
                for user in filter_users_by_email(email, prefer_verified=True)
                if user.is_active
            ]
            if users:
                target = users[0]
                # Record the accepted Google email as verified on the account so
                # allauth's password-wipe guard sees a verified address and leaves
                # the password intact (accounts created outside signup may lack an
                # EmailAddress row entirely).
                if EMAIL_AUTHENTICATION_AUTO_CONNECT and not EmailAddress.objects.filter(
                    user=target,
                    email__iexact=email,
                ).exists():
                    EmailAddress.objects.create(user=target, email=email, verified=True)
                return target, email
        return None

    def pre_social_login(self, request, sociallogin):
        provider = sociallogin.account.provider
        uid = sociallogin.account.uid
        if SocialAccount.objects.filter(
            provider=provider,
            uid=uid,
        ).exists():
            return
        for email_address in sociallogin.email_addresses:
            address = email_address.email.strip().lower()
            if not address:
                continue
            for owner_pk in _email_owner_pks(address):
                owner = User.objects.filter(pk=owner_pk).first()
                if owner is None:
                    continue
                if SocialAccount.objects.filter(
                    provider=provider,
                    user=owner,
                ).exists():
                    # Another Google identity has claimed this email address.
                    raise self._reject()
                if not email_address.verified:
                    # Unverified provider email must never silently claim an
                    # existing account.
                    raise self._reject()
                if not owner.is_active:
                    # A disabled account must never be merged into.
                    raise self._reject()

    @staticmethod
    def _reject():
        return ImmediateHttpResponse(
            HttpResponseBadRequest(
                _('User is already registered with this e-mail address.'),
            ),
        )