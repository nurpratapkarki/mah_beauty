import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

User = get_user_model()

THROTTLE_BASE = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'dj_rest_auth': '10000/min',
    },
}


@pytest.fixture(autouse=True)
def throttle_guard():
    """Neutralize the 7/min auth throttle so ordinary tests never 429.

    DRF caches ``DEFAULT_THROTTLE_RATES`` per request via its own api_settings;
    ``override_settings`` (not in-place mutation) is required to reset it.
    The dedicated throttling test overrides with a low rate + cache.clear().
    """
    with override_settings(REST_FRAMEWORK=THROTTLE_BASE):
        yield


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create_user(
        username='rita',
        email='rita@example.com',
        password='CorrectHorse9!',
        phone_number='+9779841000000',
    )