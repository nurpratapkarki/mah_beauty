import pytest

from accounts.models import User

LOGIN_URL = '/api/auth/login/'
FAIL_MSG = 'Unable to log in with provided credentials.'


@pytest.mark.django_db
class TestLoginAPI:
    def _login(self, api_client, identifier, password='CorrectHorse9!'):
        return api_client.post(
            LOGIN_URL,
            {'username': identifier, 'password': password},
            format='json',
        )

    def test_login_with_username(self, api_client, user):
        res = self._login(api_client, 'rita')
        assert res.status_code == 200
        assert set(res.data.keys()) == {'access', 'refresh', 'user'}
        assert set(res.data['user'].keys()) == {
            'id',
            'username',
            'email',
            'phone_number',
            'first_name',
            'last_name',
        }
        assert res.data['user']['username'] == 'rita'
        assert res.data['user']['email'] == 'rita@example.com'
        assert res.data['user']['phone_number'] == '+9779841000000'

    def test_login_with_email(self, api_client, user):
        res = self._login(api_client, 'RITA@Example.com')
        assert res.status_code == 200
        assert res.data['user']['id'] == user.id

    def test_login_with_phone(self, api_client, user):
        res = self._login(api_client, '9841000000')
        assert res.status_code == 200
        assert res.data['user']['id'] == user.id

    def test_login_missing_password_is_400(self, api_client, user):
        res = api_client.post(LOGIN_URL, {'username': 'rita'}, format='json')
        assert res.status_code == 400
        assert 'password' in res.data

    def test_login_wrong_password_generic(self, api_client, user):
        res = self._login(api_client, 'rita', password='nope')
        assert res.status_code == 400
        assert res.data == {'non_field_errors': [FAIL_MSG]}

    def test_login_unknown_identifier_generic(self, api_client, user):
        res = self._login(api_client, 'ghost')
        assert res.status_code == 400
        assert res.data == {'non_field_errors': [FAIL_MSG]}

    def test_failure_parity(self, api_client, user):
        """Wrong password and unknown identifier return byte-identical bodies."""
        wrong = self._login(api_client, 'rita', password='nope')
        unknown = self._login(api_client, 'ghost')
        assert wrong.status_code == unknown.status_code
        assert wrong.content == unknown.content

    def test_disabled_user_generic(self, api_client):
        disabled = User.objects.create_user(
            username='sleepy',
            email='sleepy@example.com',
            password='CorrectHorse9!',
            phone_number='+9779815556666',
        )
        disabled.is_active = False
        disabled.save(update_fields=['is_active'])
        res = self._login(api_client, 'sleepy')
        assert res.status_code == 400
        assert res.data == {'non_field_errors': [FAIL_MSG]}