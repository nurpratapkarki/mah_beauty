import pytest

from shop.payments.config import EsewaConfig
from shop.payments.errors import EsewaConfigurationError


@pytest.fixture
def esewa_settings(settings):
    settings.ESEWA_MERCHANT_CODE = "EPAYTEST"
    settings.ESEWA_SECRET_KEY = "8gBm/:&EnhH.1/q"
    settings.ESEWA_SANDBOX = True
    settings.ESEWA_BASE_URL = ""
    settings.ESEWA_SUCCESS_URL = "http://localhost:8000/success"
    settings.ESEWA_FAILURE_URL = "http://localhost:8000/failure"
    return settings


def test_from_settings_valid(esewa_settings):
    config = EsewaConfig.from_settings()
    assert config.merchant_code == "EPAYTEST"
    assert config.secret_key == "8gBm/:&EnhH.1/q"
    assert config.sandbox is True
    assert config.is_production is False


def test_from_settings_missing_merchant_code(esewa_settings):
    esewa_settings.ESEWA_MERCHANT_CODE = ""
    with pytest.raises(EsewaConfigurationError, match="ESEWA_MERCHANT_CODE"):
        EsewaConfig.from_settings()


def test_from_settings_missing_secret_key(esewa_settings):
    esewa_settings.ESEWA_SECRET_KEY = ""
    with pytest.raises(EsewaConfigurationError, match="ESEWA_SECRET_KEY"):
        EsewaConfig.from_settings()


def test_sandbox_payment_url(esewa_settings):
    config = EsewaConfig.from_settings()
    assert config.payment_url == "https://rc-epay.esewa.com.np/api/epay/main/v2/form"


def test_production_payment_url(esewa_settings):
    esewa_settings.ESEWA_SANDBOX = False
    config = EsewaConfig.from_settings()
    assert config.payment_url == "https://epay.esewa.com.np/api/epay/main/v2/form"


def test_custom_base_url(esewa_settings):
    esewa_settings.ESEWA_BASE_URL = "https://custom.esewa.com/form"
    config = EsewaConfig.from_settings()
    assert config.payment_url == "https://custom.esewa.com/form"
