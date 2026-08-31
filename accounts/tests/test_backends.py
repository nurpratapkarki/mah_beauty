import pytest
from django.contrib.auth import get_user_model
from django.http import HttpRequest

from accounts.backends import EmailOrPhoneUsernameBackend

User = get_user_model()

PASSWORD = 'CorrectHorse9!'


@pytest.mark.django_db
class TestEmailOrPhoneUsernameBackend:
    def setup_method(self):
        self.backend = EmailOrPhoneUsernameBackend()

    def _auth(self, identifier, password=PASSWORD):
        return self.backend.authenticate(
            request=HttpRequest(),
            username=identifier,
            password=password,
        )

    def test_username(self, user):
        assert self._auth('rita') == user

    def test_username_case_insensitive(self, user):
        assert self._auth('RITA') == user

    def test_email_case_insensitive(self, user):
        assert self._auth('RITA@EXAMPLE.COM') == user

    def test_phone_e164(self, user):
        assert self._auth('+9779841000000') == user

    def test_phone_bare_10_digit_normalized(self, user):
        assert self._auth('9841000000') == user

    def test_phone_funky_formatting_normalized(self, user):
        assert self._auth('+977 9841 000-000') == user

    def test_unknown_identifier_returns_none(self, user):
        assert self._auth('nobody') is None

    def test_wrong_password_returns_none(self, user):
        assert self._auth('rita', password='wrong-password') is None

    def test_blank_identifier_returns_none(self, user):
        assert self._auth('   ') is None

    def test_missing_credentials_returns_none(self, user):
        assert self.backend.authenticate(request=HttpRequest()) is None

    def test_disabled_user_denied(self, user):
        user.is_active = False
        user.save(update_fields=['is_active'])
        assert self._auth('rita') is None

    def test_duplicate_match_fails_closed(self, user):
        other = User.objects.create_user(
            username='bob',
            email='bob@example.com',
            password=PASSWORD,
            phone_number='+9779811111111',
        )
        # Force a second account to collide on email__iexact (case only; the
        # underlying UNIQUE constraint is byte-case-sensitive in SQLite).
        User.objects.filter(pk=other.pk).update(email='RITA@example.com')
        assert self._auth('rita@example.com') is None
        assert self._auth('rita@example.com', password=PASSWORD) is None

    @pytest.mark.django_db
    def test_get_user_roundtrip(self, user):
        assert self.backend.get_user(user.pk) == user

    def test_get_user_unknown_returns_none(self):
        assert self.backend.get_user(999999) is None