import pytest
from allauth.account.forms import default_token_generator
from allauth.account.utils import user_pk_to_url_str
from django.core import mail

RESET_URL = '/api/auth/password/reset/'
RESET_OK = 'Password reset e-mail has been sent.'


@pytest.fixture(autouse=True)
def clear_outbox():
    # Django's test runner swaps the configured MAILER for the locmem backend;
    # reset the outbox collection per test (pytest does not run TestCase.setUp).
    mail.outbox = []
    yield
    mail.outbox = []


@pytest.mark.django_db
class TestPasswordReset:
    def test_reset_by_email_delivers_link(self, api_client, user):
        res = api_client.post(RESET_URL, {'email': 'rita@example.com'}, format='json')
        assert res.status_code == 200
        assert res.data == {'detail': RESET_OK}
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ['rita@example.com']
        uid = user_pk_to_url_str(user)
        assert f'/{uid}/' in mail.outbox[0].body

    def test_reset_by_phone_delivers_link(self, api_client, user):
        res = api_client.post(RESET_URL, {'email': '9841000000'}, format='json')
        assert res.status_code == 200
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ['rita@example.com']

    def test_reset_by_phone_e164(self, api_client, user):
        res = api_client.post(
            RESET_URL,
            {'email': '+9779841000000'},
            format='json',
        )
        assert res.status_code == 200
        assert len(mail.outbox) == 1

    def test_unknown_identifier_identical_response(self, api_client, user):
        known = api_client.post(RESET_URL, {'email': 'rita@example.com'}, format='json')
        variants = [
            'nobody@example.com',
            '9840000000',
            '+9779800000000',
            'not-an-email',
            'zzz',
        ]
        for identifier in variants:
            res = api_client.post(RESET_URL, {'email': identifier}, format='json')
            assert res.status_code == 200
            assert res.data == {'detail': RESET_OK}
            assert res.content == known.content  # byte-identical, no enumeration
        assert len(mail.outbox) == 1  # only the known request sent mail

    def test_confirm_reset_valid_uid_token(self, api_client, user):
        uid = user_pk_to_url_str(user)
        token = default_token_generator.make_token(user)
        res = api_client.post(
            '/api/auth/password/reset/confirm/',
            {
                'uid': uid,
                'token': token,
                'new_password1': 'NewCorrectHorse9!',
                'new_password2': 'NewCorrectHorse9!',
            },
            format='json',
        )
        assert res.status_code == 200
        assert res.data == {'detail': 'Password has been reset with the new password.'}

        old = api_client.post(
            '/api/auth/login/',
            {'username': 'rita', 'password': 'CorrectHorse9!'},
            format='json',
        )
        new = api_client.post(
            '/api/auth/login/',
            {'username': 'rita', 'password': 'NewCorrectHorse9!'},
            format='json',
        )
        assert old.status_code == 400
        assert new.status_code == 200
        assert new.data['user']['id'] == user.id

    def test_confirm_replay_token_rejected(self, api_client, user):
        uid = user_pk_to_url_str(user)
        token = default_token_generator.make_token(user)
        payload = {
            'uid': uid,
            'token': token,
            'new_password1': 'NewCorrectHorse9!',
            'new_password2': 'NewCorrectHorse9!',
        }
        first = api_client.post(
            '/api/auth/password/reset/confirm/', payload, format='json',
        )
        assert first.status_code == 200

        replay = api_client.post(
            '/api/auth/password/reset/confirm/', payload, format='json',
        )
        assert replay.status_code == 400
        assert 'token' in replay.data

    def test_confirm_invalid_uid_rejected(self, api_client, user):
        res = api_client.post(
            '/api/auth/password/reset/confirm/',
            {
                'uid': 'garbage',
                'token': 'garbage',
                'new_password1': 'NewCorrectHorse9!',
                'new_password2': 'NewCorrectHorse9!',
            },
            format='json',
        )
        assert res.status_code == 400
        assert 'uid' in res.data