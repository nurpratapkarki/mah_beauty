import pytest
import requests_mock
from rest_framework.test import APIClient

from shop.models import Order, PaymentMethod
from shop.payments.fonepay import STATUS_PATH

pytestmark = pytest.mark.django_db


def _set_prn(order, prn="FP-abc123", method=PaymentMethod.FONEPAY):
    Order.objects.filter(pk=order.pk).update(prn=prn, payment_method=method)
    order.refresh_from_db()
    return order


def test_status_confirmed(fonepay_settings, order):
    order = _set_prn(order)
    client = APIClient()
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{STATUS_PATH}",
            json={
                "prn": order.prn,
                "paymentStatus": "COMPLETED",
                "fonepayTraceId": "trace-1",
                "totalTransactionAmount": "1500.00",
            },
        )
        response = client.post(
            "/api/payments/fonepay/status/",
            {"prn": order.prn},
            format="json",
        )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "success"
    assert body["message"] == "Payment successful"
    assert body["payment_status"] == "completed"
    assert body["is_paid"] is True
    assert body["order_status"] == "confirmed"
    assert body["gateway_reference"] == "trace-1"

    order.refresh_from_db()
    assert order.is_paid is True
    assert order.gateway_reference == "trace-1"
    assert order.payment_status == "completed"
    assert order.status == "confirmed"


def test_status_pending(fonepay_settings, order):
    order = _set_prn(order)
    client = APIClient()
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{STATUS_PATH}",
            json={"prn": order.prn, "paymentStatus": "pending"},
        )
        response = client.post(
            "/api/payments/fonepay/status/",
            {"prn": order.prn},
            format="json",
        )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "pending"
    assert body["message"].startswith("Payment is pending")
    assert body["is_paid"] is False
    assert body["order_status"] == "pending"

    order.refresh_from_db()
    assert order.is_paid is False
    assert order.status == "pending"
    assert order.payment_status == "pending"


def test_status_failed(fonepay_settings, order):
    order = _set_prn(order)
    client = APIClient()
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{STATUS_PATH}",
            json={"prn": order.prn, "paymentStatus": "failed"},
        )
        response = client.post(
            "/api/payments/fonepay/status/",
            {"prn": order.prn},
            format="json",
        )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "failed"
    assert body["message"] == "Payment failed"
    assert body["is_paid"] is False
    order.refresh_from_db()
    assert order.is_paid is False
    assert order.payment_status == "failed"


def test_status_idempotent_when_already_confirmed(fonepay_settings, order):
    order = _set_prn(order)
    order.mark_fonepay_confirmed("trace-existing", status="COMPLETED")
    client = APIClient()
    # FonePay would not be called for an already-confirmed order
    with requests_mock.Mocker() as m:
        response = client.post(
            "/api/payments/fonepay/status/",
            {"prn": order.prn},
            format="json",
        )
        assert not m.called

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.gateway_reference == "trace-existing"
    assert order.is_paid is True
    assert order.status == "confirmed"


def test_status_unknown_prn(fonepay_settings, order):
    client = APIClient()
    response = client.post(
        "/api/payments/fonepay/status/",
        {"prn": "FP-doesnotexist"},
        format="json",
    )
    assert response.status_code == 404
