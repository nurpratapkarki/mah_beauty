import pytest
from decimal import Decimal

from shop.models import Order, PaymentMethod


@pytest.fixture
def esewa_order(variant):
    return Order.objects.create(
        customer_name="Test User",
        contact_info="9841000000",
        shipping_address_line="Kumaripati",
        shipping_city="Lalitpur",
        total=Decimal("1000.00"),
        payment_method=PaymentMethod.ESEWA,
    )


@pytest.mark.django_db
def test_initiate_success(esewa_order, esewa_settings, client):
    resp = client.post(
        "/api/payments/esewa/initiate/",
        {"order_id": str(esewa_order.id)},
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "esewa_url" in body
    assert "signature" in body
    assert body["total_amount"] == "1000.00"
    assert body["product_code"] == "EPAYTEST"
    assert body["transaction_uuid"]
    # Order should have transaction_uuid saved
    esewa_order.refresh_from_db()
    assert esewa_order.transaction_uuid == body["transaction_uuid"]


@pytest.mark.django_db
def test_initiate_missing_order_id(esewa_settings, client):
    resp = client.post(
        "/api/payments/esewa/initiate/",
        {},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_initiate_order_not_found(esewa_settings, client):
    resp = client.post(
        "/api/payments/esewa/initiate/",
        {"order_id": "00000000-0000-0000-0000-000000000000"},
        content_type="application/json",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_initiate_wrong_payment_method(order, esewa_settings, client):
    """order fixture uses COD — should be rejected."""
    resp = client.post(
        "/api/payments/esewa/initiate/",
        {"order_id": str(order.id)},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "eSewa" in resp.json()["error"]


@pytest.mark.django_db
def test_initiate_already_paid(esewa_order, esewa_settings, client):
    esewa_order.is_paid = True
    esewa_order.save(update_fields=["is_paid"])
    resp = client.post(
        "/api/payments/esewa/initiate/",
        {"order_id": str(esewa_order.id)},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "already paid" in resp.json()["error"].lower()


@pytest.mark.django_db
def test_initiate_zero_total(esewa_order, esewa_settings, client):
    esewa_order.total = Decimal("0.00")
    esewa_order.save(update_fields=["total"])
    resp = client.post(
        "/api/payments/esewa/initiate/",
        {"order_id": str(esewa_order.id)},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "greater than zero" in resp.json()["error"].lower()
