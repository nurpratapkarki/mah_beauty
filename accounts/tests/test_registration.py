import pytest

from accounts.models import User

REGISTER_URL = '/api/auth/registration/'


def register_payload(**overrides):
    data = {
        'username': 'mia',
        'email': 'mia@example.com',
        'phone_number': '9841000002',
        'password1': 'CorrectHorse9!',
        'password2': 'CorrectHorse9!',
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestRegistrationAPI:
    def test_registration_success_with_immediate_tokens(self, api_client):
        res = api_client.post(REGISTER_URL, register_payload(), format='json')
        assert res.status_code == 201
        assert set(res.data.keys()) == {'access', 'refresh', 'user'}
        assert res.data['user']['email'] == 'mia@example.com'
        # FR-005: phone echoed back in normalized E.164 form.
        assert res.data['user']['phone_number'] == '+9779841000002'

        stored = User.objects.get(username='mia')
        assert stored.phone_number == '+9779841000002'

    def test_duplicate_username_identified(self, api_client):
        api_client.post(REGISTER_URL, register_payload(), format='json')
        res = api_client.post(
            REGISTER_URL,
            register_payload(username='mia'),
            format='json',
        )
        assert res.status_code == 400
        assert 'username' in res.data

    def test_duplicate_email_identified(self, api_client):
        api_client.post(REGISTER_URL, register_payload(), format='json')
        res = api_client.post(
            REGISTER_URL,
            register_payload(email='MIA@example.com'),
            format='json',
        )
        assert res.status_code == 400
        assert 'email' in res.data

    def test_duplicate_phone_identified(self, api_client):
        api_client.post(REGISTER_URL, register_payload(), format='json')
        res = api_client.post(
            REGISTER_URL,
            register_payload(phone_number='9841000002'),
            format='json',
        )
        assert res.status_code == 400
        assert 'phone_number' in res.data

    def test_invalid_phone_identified(self, api_client):
        res = api_client.post(
            REGISTER_URL,
            register_payload(phone_number='123'),
            format='json',
        )
        assert res.status_code == 400
        assert 'phone_number' in res.data

    def test_invalid_email_rejected(self, api_client):
        res = api_client.post(
            REGISTER_URL,
            register_payload(email='not-an-email'),
            format='json',
        )
        assert res.status_code == 400
        assert 'email' in res.data

    def test_mismatched_passwords_rejected(self, api_client):
        res = api_client.post(
            REGISTER_URL,
            register_payload(password2='DifferentPass1!'),
            format='json',
        )
        assert res.status_code == 400
        assert 'non_field_errors' in res.data
        assert User.objects.count() == 0

    def test_weak_password_rejected(self, api_client):
        res = api_client.post(
            REGISTER_URL,
            register_payload(password1='password', password2='password'),
            format='json',
        )
        assert res.status_code == 400
        assert User.objects.count() == 0

    def test_registered_user_can_login(self, api_client):
        api_client.post(REGISTER_URL, register_payload(), format='json')
        ok = api_client.post(
            '/api/auth/login/',
            {'username': 'mia', 'password': 'CorrectHorse9!'},
            format='json',
        )
        assert ok.status_code == 200