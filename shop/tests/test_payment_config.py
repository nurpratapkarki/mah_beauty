import pytest

from shop.payments.config import FonepayConfig
from shop.payments.errors import FonepayConfigurationError

pytestmark = pytest.mark.django_db


def test_config_raises_when_missing(settings):
    for attr in (
        "FONEPAY_USERNAME",
        "FONEPAY_PASSWORD",
        "FONEPAY_MERCHANT_CODE",
        "FONEPAY_SECRET_KEY",
    ):
        try:
            delattr(settings, attr)
        except AttributeError:
            pass
    with pytest.raises(FonepayConfigurationError):
        FonepayConfig.from_settings()


def test_config_reads_values(fonepay_settings):
    config = FonepayConfig.from_settings()
    assert config.username == "testuser"
    assert config.merchant_code == "MERCH01"
    assert config.sandbox is True
    assert config.is_production is False


def test_config_production_when_sandbox_false(fonepay_settings):
    settings = fonepay_settings
    settings.FONEPAY_SANDBOX = False
    config = FonepayConfig.from_settings()
    assert config.sandbox is False
    assert config.is_production is True
