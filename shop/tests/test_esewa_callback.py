import base64
import json

import pytest
from decimal import Decimal

from shop.models import Order, PaymentMethod
from shop.payments.esewa import generate_esewa_signature

SIGNED_FIELDS = "transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names"


@pytest.fixture
def esewa_order(variant):
    return Order.objects.create(
        customer_name="Test User",
        contact_info="9841000000",
        shipping_address_line="Kumaripati",
        shipping_city="Lalitpur",
        total=Decimal("1000.00"),
        payment_method=PaymentMethod.ESEWA,
        transaction_uuid="test-uuid-123",
    )


def _make_callback_data(data_dict):
    return base64.b64encode(json.dumps(data_dict).encode()).decode()


def _make_signature(transaction_code, status, total_amount, transaction_uuid, product_code, secret_key, signed_field_names):
    """Generate signature matching the verification function's field iteration."""
    import hmac, hashlib, base64 as b64
    data = f"transaction_code={transaction_code},status={status},total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code},signed_field_names={signed_field_names}"
    return b64.b64encode(
        hmac.new(secret_key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")


@pytest.mark.django_db
def test_callback_success(esewa_order, esewa_settings, client):
    sig = _make_signature("000AWEO", "COMPLETE", "1000.00", "test-uuid-123", "EPAYTEST", "8gBm/:&EnhH.1/q", SIGNED_FIELDS)
    callback_data = {
        "transaction_code": "000AWEO",
        "status": "COMPLETE",
        "total_amount": 1000.0,
        "transaction_uuid": "test-uuid-123",
        "product_code": "EPAYTEST",
        "signed_field_names": SIGNED_FIELDS,
        "signature": sig,
    }
    encoded = _make_callback_data(callback_data)
    resp = client.get(f"/api/payments/esewa/callback/?data={encoded}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETE"
    esewa_order.refresh_from_db()
    assert esewa_order.is_paid is True
    assert esewa_order.gateway_reference == "000AWEO"
    assert esewa_order.status == "confirmed"


@pytest.mark.django_db
def test_callback_invalid_signature(esewa_order, esewa_settings, client):
    callback_data = {
        "transaction_code": "000AWEO",
        "status": "COMPLETE",
        "total_amount": 1000.0,
        "transaction_uuid": "test-uuid-123",
        "product_code": "EPAYTEST",
        "signed_field_names": SIGNED_FIELDS,
        "signature": "badsignature",
    }
    encoded = _make_callback_data(callback_data)
    resp = client.get(f"/api/payments/esewa/callback/?data={encoded}")
    assert resp.status_code == 400
    esewa_order.refresh_from_db()
    assert esewa_order.is_paid is False


@pytest.mark.django_db
def test_callback_idempotent(esewa_order, esewa_settings, client):
    esewa_order.is_paid = True
    esewa_order.gateway_reference = "000AWEO"
    esewa_order.status = "confirmed"
    esewa_order.save(update_fields=["is_paid", "gateway_reference", "status"])

    sig = _make_signature("000AWEO", "COMPLETE", "1000.00", "test-uuid-123", "EPAYTEST", "8gBm/:&EnhH.1/q", SIGNED_FIELDS)
    callback_data = {
        "transaction_code": "000AWEO",
        "status": "COMPLETE",
        "total_amount": 1000.0,
        "transaction_uuid": "test-uuid-123",
        "product_code": "EPAYTEST",
        "signed_field_names": SIGNED_FIELDS,
        "signature": sig,
    }
    encoded = _make_callback_data(callback_data)
    resp = client.get(f"/api/payments/esewa/callback/?data={encoded}")
    assert resp.status_code == 200
    esewa_order.refresh_from_db()
    assert esewa_order.is_paid is True


@pytest.mark.django_db
def test_callback_failed_status(esewa_order, esewa_settings, client):
    sig = _make_signature("", "FAILED", "1000.00", "test-uuid-123", "EPAYTEST", "8gBm/:&EnhH.1/q", SIGNED_FIELDS)
    callback_data = {
        "transaction_code": "",
        "status": "FAILED",
        "total_amount": 1000.0,
        "transaction_uuid": "test-uuid-123",
        "product_code": "EPAYTEST",
        "signed_field_names": SIGNED_FIELDS,
        "signature": sig,
    }
    encoded = _make_callback_data(callback_data)
    resp = client.get(f"/api/payments/esewa/callback/?data={encoded}")
    assert resp.status_code == 200
    esewa_order.refresh_from_db()
    assert esewa_order.is_paid is False


@pytest.mark.django_db
def test_callback_missing_data(esewa_settings, client):
    resp = client.get("/api/payments/esewa/callback/")
    assert resp.status_code == 400
