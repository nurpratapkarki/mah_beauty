import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

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
        transaction_uuid="status-test-uuid",
    )


@pytest.mark.django_db
def test_status_complete(esewa_order, esewa_settings, client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "product_code": "EPAYTEST",
        "transaction_uuid": "status-test-uuid",
        "total_amount": 1000.0,
        "status": "COMPLETE",
        "ref_id": "0001TS9",
    }
    with patch("shop.payments.views.http_requests.get", return_value=mock_resp):
        resp = client.post(
            "/api/payments/esewa/status/",
            {"order_id": str(esewa_order.id)},
            content_type="application/json",
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETE"
    esewa_order.refresh_from_db()
    assert esewa_order.is_paid is True
    assert esewa_order.gateway_reference == "0001TS9"


@pytest.mark.django_db
def test_status_pending(esewa_order, esewa_settings, client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "product_code": "EPAYTEST",
        "transaction_uuid": "status-test-uuid",
        "total_amount": 1000.0,
        "status": "PENDING",
    }
    with patch("shop.payments.views.http_requests.get", return_value=mock_resp):
        resp = client.post(
            "/api/payments/esewa/status/",
            {"order_id": str(esewa_order.id)},
            content_type="application/json",
        )
    assert resp.status_code == 200
    esewa_order.refresh_from_db()
    assert esewa_order.is_paid is False
    assert esewa_order.payment_status == "PENDING"


@pytest.mark.django_db
def test_status_not_found(esewa_order, esewa_settings, client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "product_code": "EPAYTEST",
        "transaction_uuid": "status-test-uuid",
        "total_amount": 1000.0,
        "status": "NOT_FOUND",
    }
    with patch("shop.payments.views.http_requests.get", return_value=mock_resp):
        resp = client.post(
            "/api/payments/esewa/status/",
            {"order_id": str(esewa_order.id)},
            content_type="application/json",
        )
    assert resp.status_code == 200
    esewa_order.refresh_from_db()
    assert esewa_order.is_paid is False


@pytest.mark.django_db
def test_status_idempotent(esewa_order, esewa_settings, client):
    esewa_order.is_paid = True
    esewa_order.gateway_reference = "0001TS9"
    esewa_order.status = "confirmed"
    esewa_order.payment_status = "COMPLETE"
    esewa_order.save(update_fields=["is_paid", "gateway_reference", "status", "payment_status"])

    resp = client.post(
        "/api/payments/esewa/status/",
        {"order_id": str(esewa_order.id)},
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETE"
    assert body["is_paid"] is True


@pytest.mark.django_db
def test_status_missing_order(esewa_settings, client):
    resp = client.post(
        "/api/payments/esewa/status/",
        {"order_id": "00000000-0000-0000-0000-000000000000"},
        content_type="application/json",
    )
    assert resp.status_code == 404
