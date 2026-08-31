import base64
import json
import hmac
import hashlib

import pytest
from decimal import Decimal

from shop.models import Order, PaymentMethod

SIGNED_FIELDS = "transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names"


def _make_callback_signature(transaction_code, status, total_amount, transaction_uuid, product_code, secret_key):
    data = f"transaction_code={transaction_code},status={status},total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code},signed_field_names={SIGNED_FIELDS}"
    return base64.b64encode(
        hmac.new(secret_key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")


@pytest.fixture
def esewa_order(variant):
    order = Order.objects.create(
        customer_name="Test User",
        contact_info="9841000000",
        shipping_address_line="Kumaripati",
        shipping_city="Lalitpur",
        total=Decimal("1000.00"),
        payment_method=PaymentMethod.ESEWA,
        transaction_uuid="test-uuid-integration",
    )
    from shop.models import OrderItem
    OrderItem.objects.create(order=order, variant=variant, quantity=1, price=Decimal("1000.00"))
    return order


@pytest.mark.django_db
def test_full_eSewa_journey(esewa_order, esewa_settings, client):
    """Initiate → callback → order paid+confirmed, stock safe."""
    # Step 1: Initiate payment
    resp = client.post(
        "/api/payments/esewa/initiate/",
        {"order_id": str(esewa_order.id)},
        content_type="application/json",
    )
    assert resp.status_code == 200
    payload = resp.json()
    transaction_uuid = payload["transaction_uuid"]

    # Step 2: Simulate eSewa callback
    sig = _make_callback_signature(
        "INT-TEST-001", "COMPLETE", "1000.00", transaction_uuid, "EPAYTEST", "8gBm/:&EnhH.1/q"
    )
    callback_data = {
        "transaction_code": "INT-TEST-001",
        "status": "COMPLETE",
        "total_amount": 1000.0,
        "transaction_uuid": transaction_uuid,
        "product_code": "EPAYTEST",
        "signed_field_names": SIGNED_FIELDS,
        "signature": sig,
    }
    encoded = base64.b64encode(json.dumps(callback_data).encode()).decode()
    resp = client.get(f"/api/payments/esewa/callback/?data={encoded}")
    assert resp.status_code == 200

    # Step 3: Verify order state
    esewa_order.refresh_from_db()
    assert esewa_order.is_paid is True
    assert esewa_order.status == "confirmed"
    assert esewa_order.gateway_reference == "INT-TEST-001"
    assert esewa_order.payment_status == "COMPLETE"

    # Step 4: Verify stock was decremented by the OrderItem creation signal
    esewa_order.items.first().variant.refresh_from_db()
    assert esewa_order.items.first().variant.stock_quantity == 9
