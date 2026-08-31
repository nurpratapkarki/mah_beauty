import pytest
from django.core.cache import cache
from django.test import override_settings

from accounts.tests.conftest import THROTTLE_BASE

LOGIN_URL = '/api/auth/login/'

LOW_REST_FRAMEWORK = {
    **THROTTLE_BASE,
    'DEFAULT_THROTTLE_RATES': {'dj_rest_auth': '7/min'},
}


@pytest.mark.django_db
class TestLoginThrottling:
    """FR-015: backoff-not-lockout on auth endpoints."""

    def setup_method(self):
        cache.clear()

    def test_seven_rapid_failures_blocked_then_usable_after(self, api_client, user):
        with override_settings(REST_FRAMEWORK=LOW_REST_FRAMEWORK):
            statuses = []
            for _ in range(8):
                res = api_client.post(
                    LOGIN_URL,
                    {'username': 'ghost', 'password': 'x'},
                    format='json',
                )
                statuses.append(res.status_code)

        assert statuses[:7] == [400] * 7
        assert statuses[7] == 429
        assert 'throttled' in res.data['detail'].lower()

        # Backoff, never lockout: clearing the throttle (time passing) or IP
        # rotation restores access; the account itself is never disabled.
        cache.clear()
        ok = api_client.post(
            LOGIN_URL,
            {'username': user.username, 'password': 'CorrectHorse9!'},
            format='json',
        )
        assert ok.status_code == 200