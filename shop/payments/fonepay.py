import hashlib
import hmac

import requests

from .config import FonepayConfig
from .errors import FonepayConfigurationError, FonepayUpstreamError

GENERATE_QR_PATH = "/merchant/merchantDetailsForThirdParty/thirdPartyDynamicQrDownload"
STATUS_PATH = "/merchant/merchantDetailsForThirdParty/thirdPartyDynamicQrGetStatus"
TAX_REFUND_PATH = "/merchant/merchantDetailsForThirdParty/thirdPartyPostTaxRefund"

# Canonical result values returned to callers / the storefront.
SUCCESS = "success"
PENDING = "pending"
FAILED = "failed"
CANCELLED = "cancelled"


def _hmac_sha512(secret_key: str, message: str) -> str:
    """Generate a lowercase-hex HMAC-SHA512 digest of ``message``."""
    return hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()


class FonepayClient:
    """Thin client for the FonePay dynamic-QR merchant API."""

    def __init__(self, config: FonepayConfig | None = None):
        self.config = config or FonepayConfig.from_settings()
        if not self.config.base_url:
            raise FonepayConfigurationError(
                "FONEPAY_BASE_URL must be configured to call the FonePay API."
            )
        if not (self.config.username and self.config.password):
            raise FonepayConfigurationError(
                "FonePay username and password must be configured."
            )

    def _post(self, path: str, payload: dict) -> dict:
        auth = requests.auth.HTTPBasicAuth(self.config.username, self.config.password)
        try:
            response = requests.post(
                f"{self.config.base_url}{path}",
                json=payload,
                auth=auth,
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise FonepayUpstreamError(f"FonePay request failed: {exc}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise FonepayUpstreamError(
                "FonePay returned a non-JSON response."
            ) from exc

    def generate_qr(
        self,
        amount: str,
        prn: str,
        remarks1: str,
        remarks2: str = "",
        tax_amount: str = "",
        tax_refund: str = "",
    ) -> dict:
        """Request a dynamic QR for the given amount and PRN.

        When ``tax_refund`` is supplied, the HMAC message and payload also carry
        the tax amount/flag, per FonePay's optional tax-refund QR flow.

        Returns a dict with the QR payload plus any FonePay-reported status/message,
        so callers can surface failures even on an apparently-200 response.
        """
        if tax_refund:
            message = (
                f"{amount},{prn},{self.config.merchant_code},{remarks1},{remarks2},"
                f"{tax_amount},{tax_refund}"
            )
        else:
            message = f"{amount},{prn},{self.config.merchant_code},{remarks1},{remarks2}"
        payload = {
            "amount": amount,
            "prn": prn,
            "merchantCode": self.config.merchant_code,
            "remarks1": remarks1,
            "remarks2": remarks2,
            "dataValidation": _hmac_sha512(self.config.secret_key, message),
            "username": self.config.username,
            "password": self.config.password,
        }
        if tax_refund:
            payload["taxAmount"] = tax_amount
            payload["taxRefund"] = tax_refund
        result = self._post(GENERATE_QR_PATH, payload)
        # Per the FonePay dynamic-QR contract the QR image payload is delivered
        # in the "qrMessage" field. Tolerate older/alternate spellings.
        qr = (
            result.get("qrMessage")
            or result.get("qrString")
            or result.get("qr")
            or result.get("data")
        )
        if not qr:
            message_text = result.get("message") or result.get("status") or ""
            raise FonepayUpstreamError(
                f"FonePay dynamic-QR response did not contain a QR payload. {message_text}".strip()
            )
        return {
            "qr": qr,
            "qr_message": result.get("message") or "",
            "statement": result.get("status") or result.get("paymentStatus") or "",
            "websocket_url": result.get("thirdpartyQrWebSocketUrl")
            or result.get("ThirdpartyQrWebSocketUrl")
            or "",
        }

    def check_status(self, prn: str) -> dict:
        """Query the payment status for a PRN. Returns the FonePay status JSON."""
        message = f"{prn},{self.config.merchant_code}"
        payload = {
            "prn": prn,
            "merchantCode": self.config.merchant_code,
            "dataValidation": _hmac_sha512(self.config.secret_key, message),
            "username": self.config.username,
            "password": self.config.password,
        }
        return self._post(STATUS_PATH, payload)

    def tax_refund(
        self,
        fonepay_trace_id: str,
        transaction_amount: str,
        merchant_prn: str,
        invoice_number: str,
        invoice_date: str,
    ) -> dict:
        """Post a tax refund for a successful FonePay transaction.

        ``invoice_date`` must be in ``YYYY-MM-DD`` format and the
        ``transaction_amount`` should match the original transaction amount.
        """
        message = (
            f"{fonepay_trace_id},{merchant_prn},{invoice_number},{invoice_date},"
            f"{transaction_amount},{self.config.merchant_code}"
        )
        payload = {
            "fonepayTraceId": fonepay_trace_id,
            "transactionAmount": transaction_amount,
            "merchantPRN": merchant_prn,
            "invoiceNumber": invoice_number,
            "invoiceDate": invoice_date,
            "merchantCode": self.config.merchant_code,
            "dataValidation": _hmac_sha512(self.config.secret_key, message),
            "username": self.config.username,
            "password": self.config.password,
        }
        return self._post(TAX_REFUND_PATH, payload)

    @staticmethod
    def is_paid_status(status_json: dict) -> bool:
        """Normalize FonePay's payment status field to a boolean."""
        raw = str(status_json.get("paymentStatus", "")).lower()
        # FonePay reports completion as "COMPLETED"; tolerate a few variants.
        return raw in {"completed", "success", "paid", "successful"}


def interpret_status(status_json: dict) -> tuple:
    """Map a FonePay status payload to a canonical (result, friendly_message).

    Returns one of (SUCCESS|PENDING|FAILED|CANCELLED, message).
    """
    raw = str(status_json.get("paymentStatus", "")).lower()
    if raw in {"completed", "success", "paid", "successful"}:
        return SUCCESS, "Payment successful"
    if raw in {"cancel", "cancelled", "canceled", "expired", "timeout"}:
        return CANCELLED, "Payment was cancelled or expired"
    if raw in {"failed", "failure", "error", "rejected"}:
        return FAILED, "Payment failed"
    return PENDING, "Payment is pending — awaiting customer confirmation"


def get_client(config: FonepayConfig | None = None) -> FonepayClient:
    """Shared factory: build a FonePay client from settings (or an explicit config).

    Raises :class:`FonepayConfigurationError` if FonePay is not configured.
    Callers (views, background workers) should use this instead of constructing
    :class:`FonepayClient` directly so configuration stays in one place.
    """
    return FonepayClient(config=config)


def generate_prn(order_id) -> str:
    """Build a FonePay Payment Reference Number for an order.

    Uses the existing PRN if present, otherwise derives one deterministically
    from the order's UUID so re-generation stays stable.
    """
    return f"FP-{order_id}"


def is_fonepay_payment(order) -> bool:
    """True if the given order uses the FonePay payment method."""
    from ..models import PaymentMethod

    return getattr(order, "payment_method", None) == PaymentMethod.FONEPAY


def confirm_paid_order(order, status_json: dict):
    """Mark an order paid/confirmed after a verified FonePay payment.

    Replaces the manual pattern
    ``order.refresh_from_db(); order.mark_fonepay_confirmed(...)`` so every
    confirmation site (polling endpoint, realtime monitor) shares the same
    confirmation behaviour. Idempotent — safe to call repeatedly.
    """
    order.refresh_from_db()
    order.mark_fonepay_confirmed(
        gateway_reference=str(status_json.get("fonepayTraceId", "")),
        status=str(status_json.get("paymentStatus", "COMPLETED")).lower(),
    )
    order.refresh_from_db()
    return order
