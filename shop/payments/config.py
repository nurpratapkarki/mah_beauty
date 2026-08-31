from dataclasses import dataclass

from django.conf import settings

from .errors import EsewaConfigurationError


@dataclass(frozen=True)
class EsewaConfig:
    merchant_code: str
    secret_key: str
    sandbox: bool = True
    base_url: str = ""
    success_url: str = ""
    failure_url: str = ""

    @property
    def is_production(self) -> bool:
        return not self.sandbox

    @property
    def payment_url(self) -> str:
        if self.base_url:
            return self.base_url
        if self.sandbox:
            return "https://rc-epay.esewa.com.np/api/epay/main/v2/form"
        return "https://epay.esewa.com.np/api/epay/main/v2/form"

    @property
    def status_check_url(self) -> str:
        if self.sandbox:
            return "https://rc.esewa.com.np/api/epay/transaction/status/"
        return "https://esewa.com.np/api/epay/transaction/status/"

    @classmethod
    def from_settings(cls):
        merchant_code = getattr(settings, "ESEWA_MERCHANT_CODE", "")
        secret_key = getattr(settings, "ESEWA_SECRET_KEY", "")
        if not merchant_code or not secret_key:
            missing = []
            if not merchant_code:
                missing.append("ESEWA_MERCHANT_CODE")
            if not secret_key:
                missing.append("ESEWA_SECRET_KEY")
            raise EsewaConfigurationError(
                f"Missing required eSewa settings: {', '.join(missing)}"
            )
        return cls(
            merchant_code=merchant_code,
            secret_key=secret_key,
            sandbox=bool(getattr(settings, "ESEWA_SANDBOX", True)),
            base_url=getattr(settings, "ESEWA_BASE_URL", ""),
            success_url=getattr(settings, "ESEWA_SUCCESS_URL", ""),
            failure_url=getattr(settings, "ESEWA_FAILURE_URL", ""),
        )
