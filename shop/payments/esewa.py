import base64
import hashlib
import hmac
import json
import uuid

from .config import EsewaConfig
from .errors import EsewaConfigurationError


def generate_esewa_signature(total_amount, transaction_uuid, product_code, secret_key):
    """Generate HMAC-SHA256 signature for eSewa payment payload.

    The signing string format is exact: ``total_amount=X,transaction_uuid=Y,product_code=Z``
    with no spaces after commas.
    """
    data = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"
    return base64.b64encode(
        hmac.new(
            secret_key.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")


def build_esewa_payload(order, config=None):
    """Build the signed eSewa form payload for an order.

    Returns a dict with all form fields needed to POST to eSewa, plus the
    ``esewa_url`` for the redirect target. The frontend should auto-submit
    a hidden form with these fields.
    """
    config = config or EsewaConfig.from_settings()

    transaction_uuid = str(uuid.uuid4())
    total_amount = str(order.total)
    tax_amount = "0"
    service_charge = "0"
    delivery_charge = "0"

    signature = generate_esewa_signature(
        total_amount=total_amount,
        transaction_uuid=transaction_uuid,
        product_code=config.merchant_code,
        secret_key=config.secret_key,
    )

    return {
        "amount": total_amount,
        "tax_amount": tax_amount,
        "product_service_charge": service_charge,
        "product_delivery_charge": delivery_charge,
        "total_amount": total_amount,
        "transaction_uuid": transaction_uuid,
        "product_code": config.merchant_code,
        "success_url": config.success_url,
        "failure_url": config.failure_url,
        "signed_field_names": "total_amount,transaction_uuid,product_code",
        "signature": signature,
        "esewa_url": config.payment_url,
    }


def verify_esewa_signature(response_data, secret_key):
    """Verify the HMAC-SHA256 signature on an eSewa callback response.

    ``response_data`` is the decoded JSON from the base64-encoded callback.
    Returns True if the signature is valid, False otherwise.
    """
    try:
        signed_field_names = response_data.get("signed_field_names", "")
        if not signed_field_names:
            return False

        fields = [f.strip() for f in signed_field_names.split(",")]
        values = []
        for field in fields:
            val = response_data.get(field)
            if val is None:
                return False
            # eSewa returns total_amount as a float; format to 2 decimal places
            # to match the signing string format used during initiation.
            if field == "total_amount":
                val = f"{float(val):.2f}"
            values.append(f"{field}={val}")

        data = ",".join(values)
        expected_signature = base64.b64encode(
            hmac.new(
                secret_key.encode("utf-8"),
                data.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        return hmac.compare_digest(expected_signature, response_data.get("signature", ""))
    except (ValueError, TypeError):
        return False


def decode_esewa_callback(encoded_data):
    """Decode the base64-encoded callback data from eSewa.

    Returns the parsed JSON dict, or raises ValueError on decode failure.
    """
    try:
        decoded = base64.b64decode(encoded_data).decode("utf-8")
        return json.loads(decoded)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid eSewa callback data: {exc}") from exc
