from dataclasses import dataclass

from django.conf import settings

from .errors import FonepayConfigurationError


@dataclass(frozen=True)
class FonepayConfig:
    username: str
    password: str
    merchant_code: str
    secret_key: str
    base_url: str
    sandbox: bool = True

    @property
    def is_production(self) -> bool:
        return not self.sandbox

    @classmethod
    def from_settings(cls):
        required = {
            "FONEPAY_USERNAME": getattr(settings, "FONEPAY_USERNAME", ""),
            "FONEPAY_PASSWORD": getattr(settings, "FONEPAY_PASSWORD", ""),
            "FONEPAY_MERCHANT_CODE": getattr(settings, "FONEPAY_MERCHANT_CODE", ""),
            "FONEPAY_SECRET_KEY": getattr(settings, "FONEPAY_SECRET_KEY", ""),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise FonepayConfigurationError(
                f"Missing required FonePay settings: {', '.join(missing)}"
            )
        return cls(
            username=required["FONEPAY_USERNAME"],
            password=required["FONEPAY_PASSWORD"],
            merchant_code=required["FONEPAY_MERCHANT_CODE"],
            secret_key=required["FONEPAY_SECRET_KEY"],
            base_url=getattr(settings, "FONEPAY_BASE_URL", ""),
            sandbox=bool(getattr(settings, "FONEPAY_SANDBOX", True)),
        )
