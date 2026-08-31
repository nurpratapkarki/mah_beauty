from unittest import mock

import pytest
import requests
from allauth.socialaccount.models import SocialAccount

from accounts.models import User

GOOGLE_URL = '/api/auth/google/'

GOOGLE_PROVIDER_SETTINGS = {
    'google': {
        'APP': {
            'client_id': 'test-client.apps.googleusercontent.com',
            'secret': 'test-secret',
            'key': '',
        },
    },
}

PATCH_TARGET = (
    'allauth.socialaccount.providers.google.views.GoogleOAuth2Adapter'
    '._fetch_user_info'
)


def profile(**overrides):
    data = {
        'sub': 'g-123',
        'email': 'tina@gmail.com',
        'email_verified': True,
        'name': 'Tina Turner',
        'given_name': 'Tina',
        'family_name': 'Turner',
        'picture': 'https://example.com/tina.png',
        'locale': 'en',
    }
    data.update(overrides)
    return data


@pytest.fixture
def google_configured(settings):
    settings.SOCIALACCOUNT_PROVIDERS = GOOGLE_PROVIDER_SETTINGS
    return settings


@pytest.mark.django_db
class TestGoogleLogin:

    def _post(self, api_client, mocked_profile):
        with mock.patch(PATCH_TARGET, return_value=mocked_profile):
            return api_client.post(
                GOOGLE_URL,
                {'access_token': 'valid-token'},
                format='json',
            )

    def _post_failure(self, api_client, exc=None):
        exc = exc or requests.HTTPError('401 Unauthorized')
        with mock.patch(PATCH_TARGET, side_effect=exc):
            return api_client.post(
                GOOGLE_URL,
                {'access_token': 'garbage'},
                format='json',
            )

    def test_missing_token_400(self, api_client, google_configured):
        res = api_client.post(GOOGLE_URL, {}, format='json')
        assert res.status_code == 400

    def test_first_time_creates_account(self, api_client, google_configured):
        res = self._post(api_client, profile(sub='g-1', email='first@gmail.com'))
        assert res.status_code == 200
        assert set(res.data.keys()) == {'access', 'refresh', 'user'}

        user = User.objects.get()
        assert user.email == 'first@gmail.com'
        assert user.username
        assert user.phone_number is None  # FR-006: no phone from Google
        assert user.check_password('') is False
        assert user.has_usable_password() is False
        assert SocialAccount.objects.filter(provider='google', uid='g-1').get().user == user

    def test_returning_user_matched_no_duplicate(self, api_client, google_configured):
        first = self._post(api_client, profile(sub='g-2'))
        assert first.status_code == 200

        second = self._post(api_client, profile(sub='g-2'))
        assert second.status_code == 200
        assert second.data['user']['id'] == first.data['user']['id']
        assert User.objects.count() == 1
        assert SocialAccount.objects.count() == 1

    def test_invalid_token_rejected_zero_rows(self, api_client, google_configured):
        res = self._post_failure(api_client)
        assert res.status_code == 400
        assert res.data['non_field_errors'] == ['Incorrect value']
        assert User.objects.count() == 0
        assert SocialAccount.objects.count() == 0

    def test_email_on_password_account_linked(self, api_client, google_configured):
        existing = User.objects.create_user(
            username='pw-user',
            email='tina@gmail.com',
            password='StrongPass1!',
            phone_number='+9779811112222',
        )
        res = self._post(api_client, profile(sub='g-link'))
        assert res.status_code == 200
        assert res.data['user']['id'] == existing.id
        assert User.objects.count() == 1
        assert SocialAccount.objects.get(uid='g-link').user == existing

        # FR-008: password path still works after linking.
        ok = api_client.post(
            '/api/auth/login/',
            {'username': 'pw-user', 'password': 'StrongPass1!'},
            format='json',
        )
        assert ok.status_code == 200

    def test_email_owned_by_different_google_rejected(self, api_client, google_configured):
        owner = User.objects.create_user(
            username='g-owner',
            email='tina@gmail.com',
            password='StrongPass1!',
            phone_number='+9779813334444',
        )
        SocialAccount.objects.create(user=owner, provider='google', uid='g-already')

        res = self._post(api_client, profile(sub='g-new'))
        assert res.status_code == 400
        assert SocialAccount.objects.filter(uid='g-new').count() == 0
        assert SocialAccount.objects.get(uid='g-already').user == owner
        assert User.objects.count() == 1

    def test_email_not_verified_does_not_merge(self, api_client, google_configured):
        existing = User.objects.create_user(
            username='pw-user',
            email='tina@gmail.com',
            password='StrongPass1!',
            phone_number='+9779811112222',
        )
        res = self._post(api_client, profile(sub='g-nv', email_verified=False))
        # Unverified email is never silently merged: rejected, no new rows.
        assert res.status_code == 400
        assert User.objects.count() == 1
        assert SocialAccount.objects.count() == 0