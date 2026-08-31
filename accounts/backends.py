from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from accounts.validators import normalize_phone


class EmailOrPhoneUsernameBackend(ModelBackend):
    """Authenticate with username, email, OR phone number + password.

    Lookup is case-insensitive for username/email; the identifier is normalized
    as a phone (bare Nepali 10-digit numbers become ``+977...``) before a phone
    match is attempted. A conflicting match (same identifier resolving to more
    than one user) fails closed with ``None`` — never signs into the wrong
    account. Wrong password and unknown identifier both return ``None``.
    """

    def authenticate(self, request=None, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        identifier = str(username).strip()
        if not identifier:
            return None
        user_model = get_user_model()

        lookup = Q(username__iexact=identifier) | Q(email__iexact=identifier)
        phone = normalize_phone(identifier)
        if phone:
            lookup |= Q(phone_number__iexact=phone)

        try:
            user = user_model._default_manager.get(lookup)
        except user_model.DoesNotExist:
            return None
        except user_model.MultipleObjectsReturned:
            return None

        if user.check_password(password):
            return user if self.user_can_authenticate(user) else None
        return None

    def get_user(self, user_id):
        user_model = get_user_model()
        try:
            return user_model._default_manager.get(pk=user_id)
        except user_model.DoesNotExist:
            return None