import pytest

USER_URL = '/api/auth/user/'
LOGIN_URL = '/api/auth/login/'
PASSWORD_CHANGE_URL = '/api/auth/password/change/'
LOGOUT_URL = '/api/auth/logout/'
REFRESH_URL = '/api/auth/token/refresh/'

USER_KEYS = {'id', 'username', 'email', 'phone_number', 'first_name', 'last_name'}


def login(api_client, username, password):
    res = api_client.post(
        LOGIN_URL,
        {'username': username, 'password': password},
        format='json',
    )
    assert res.status_code == 200
    return res.data['access'], res.data['refresh']


@pytest.mark.django_db
class TestProfileAPI:
    def _auth_login(self, api_client, user):
        access, refresh = login(api_client, user.username, 'CorrectHorse9!')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        return access, refresh

    def test_unauthenticated_401(self, api_client, user):
        res = api_client.get(USER_URL)
        assert res.status_code == 401

    def test_get_user_shape(self, api_client, user):
        self._auth_login(api_client, user)
        res = api_client.get(USER_URL)
        assert res.status_code == 200
        assert set(res.data.keys()) == USER_KEYS
        assert 'password' not in res.data
        assert res.data['phone_number'] == '+9779841000000'

    def test_patch_phone_normalized(self, api_client, user):
        self._auth_login(api_client, user)
        res = api_client.patch(USER_URL, {'phone_number': '9812334455'}, format='json')
        assert res.status_code == 200
        assert res.data['phone_number'] == '+9779812334455'
        user.refresh_from_db()
        assert user.phone_number == '+9779812334455'

    def test_patch_clear_phone(self, api_client, user):
        self._auth_login(api_client, user)
        res = api_client.patch(USER_URL, {'phone_number': ''}, format='json')
        assert res.status_code == 200
        assert res.data['phone_number'] is None

    def test_patch_invalid_phone_rejected(self, api_client, user):
        self._auth_login(api_client, user)
        res = api_client.patch(USER_URL, {'phone_number': '123'}, format='json')
        assert res.status_code == 400
        assert 'phone_number' in res.data

    def test_patch_email_duplicate_rejected(self, api_client, user):
        from accounts.models import User

        User.objects.create_user(
            username='other',
            email='other@example.com',
            password='CorrectHorse9!',
            phone_number='+9779817778888',
        )
        self._auth_login(api_client, user)
        res = api_client.patch(USER_URL, {'email': 'other@example.com'}, format='json')
        assert res.status_code == 400
        assert 'email' in res.data

    def test_patch_phone_duplicate_rejected(self, api_client, user):
        from accounts.models import User

        User.objects.create_user(
            username='other',
            email='other@example.com',
            password='CorrectHorse9!',
            phone_number='+9779817778888',
        )
        self._auth_login(api_client, user)
        res = api_client.patch(USER_URL, {'phone_number': '9817778888'}, format='json')
        assert res.status_code == 400
        assert 'phone_number' in res.data


@pytest.mark.django_db
class TestPasswordChange:
    def _login(self, api_client, user):
        access, _ = login(api_client, user.username, 'CorrectHorse9!')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

    def test_wrong_old_password_400(self, api_client, user):
        self._login(api_client, user)
        res = api_client.post(
            PASSWORD_CHANGE_URL,
            {
                'old_password': 'nope',
                'new_password1': 'NewCorrectHorse9!',
                'new_password2': 'NewCorrectHorse9!',
            },
            format='json',
        )
        assert res.status_code == 400
        assert 'old_password' in res.data

    def test_change_password_old_stops_working(self, api_client, user):
        self._login(api_client, user)
        res = api_client.post(
            PASSWORD_CHANGE_URL,
            {
                'old_password': 'CorrectHorse9!',
                'new_password1': 'NewCorrectHorse9!',
                'new_password2': 'NewCorrectHorse9!',
            },
            format='json',
        )
        assert res.status_code == 200
        assert 'New password has been saved.' in res.data['detail']

        api_client.credentials()
        old = api_client.post(
            LOGIN_URL,
            {'username': 'rita', 'password': 'CorrectHorse9!'},
            format='json',
        )
        new = api_client.post(
            LOGIN_URL,
            {'username': 'rita', 'password': 'NewCorrectHorse9!'},
            format='json',
        )
        assert old.status_code == 400
        assert new.status_code == 200


@pytest.mark.django_db
class TestLogout:
    def test_logout_blacklists_refresh(self, api_client, user):
        access, refresh = login(api_client, user.username, 'CorrectHorse9!')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        res = api_client.post(LOGOUT_URL, {'refresh': refresh}, format='json')
        assert res.status_code == 200
        assert 'Successfully logged out.' in res.data['detail']

        # FR-013: the logged-out refresh must no longer refresh tokens.
        res = api_client.post(REFRESH_URL, {'refresh': refresh}, format='json')
        assert res.status_code == 401

    def test_logout_missing_refresh_401(self, api_client, user):
        access, _ = login(api_client, user.username, 'CorrectHorse9!')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        res = api_client.post(LOGOUT_URL, {}, format='json')
        assert res.status_code == 401