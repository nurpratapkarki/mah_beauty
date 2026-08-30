import pytest
import requests_mock
from rest_framework.test import APIClient

from shop.models import Order, PaymentMethod
from shop.payments.fonepay import TAX_REFUND_PATH, _hmac_sha512

pytestmark = pytest.mark.django_db


def _paid_fonepay_order(order):
    from shop.models import Order

    Order.objects.filter(pk=order.pk).update(prn="PRN-1")
    order.refresh_from_db()
    order.mark_fonepay_confirmed(gateway_reference="trace-123")
    return order


def test_tax_refund_success(fonepay_settings, order):
    _paid_fonepay_order(order)
    client = APIClient()
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{TAX_REFUND_PATH}",
            json={"fonepayTraceId": 123, "message": "Success", "success": True},
        )
        response = client.post(
            "/api/payments/fonepay/refund/",
            {
                "order_id": str(order.id),
                "invoice_number": "INV-001",
                "invoice_date": "2026-08-30",
            },
            format="json",
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Success"
    assert body["fonepay_trace_id"] == 123


def test_tax_refund_request_fields(fonepay_settings, order):
    _paid_fonepay_order(order)
    client = APIClient()
    captured = {}
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{TAX_REFUND_PATH}",
            additional_matcher=lambda req: captured.update(req.json()) or True,
            json={"success": True, "message": "ok"},
        )
        client.post(
            "/api/payments/fonepay/refund/",
            {
                "order_id": str(order.id),
                "invoice_number": "INV-9",
                "invoice_date": "2026-08-30",
                "transaction_amount": "1500.00",
            },
            format="json",
        )

    expected_msg = f"trace-123,PRN-1,INV-9,2026-08-30,1500.00,{fonepay_settings.FONEPAY_MERCHANT_CODE}"
    assert captured["fonepayTraceId"] == "trace-123"
    assert captured["transactionAmount"] == "1500.00"
    assert captured["merchantPRN"] == "PRN-1"
    assert captured["invoiceNumber"] == "INV-9"
    assert captured["invoiceDate"] == "2026-08-30"
    assert captured["merchantCode"] == fonepay_settings.FONEPAY_MERCHANT_CODE
    assert captured["dataValidation"] == _hmac_sha512(
        fonepay_settings.FONEPAY_SECRET_KEY, expected_msg
    )


def test_tax_refund_rejects_unpaid(order):
    client = APIClient()
    response = client.post(
        "/api/payments/fonepay/refund/",
        {"order_id": str(order.id), "invoice_number": "INV-1", "invoice_date": "2026-08-30"},
        format="json",
    )
    assert response.status_code == 400


def test_tax_refund_requires_invoice(order):
    _paid_fonepay_order(order)
    client = APIClient()
    response = client.post(
        "/api/payments/fonepay/refund/",
        {"order_id": str(order.id), "invoice_date": "2026-08-30"},
        format="json",
    )
    assert response.status_code == 400


def test_tax_refund_requires_invoice_date(order):
    _paid_fonepay_order(order)
    client = APIClient()
    response = client.post(
        "/api/payments/fonepay/refund/",
        {"order_id": str(order.id), "invoice_number": "INV-1"},
        format="json",
    )
    assert response.status_code == 400


def test_tax_refund_rejects_wrong_payment_method(fonepay_settings, order):
    Order.objects.filter(pk=order.pk).update(payment_method=PaymentMethod.COD)
    client = APIClient()
    response = client.post(
        "/api/payments/fonepay/refund/",
        {"order_id": str(order.id), "invoice_number": "INV-1", "invoice_date": "2026-08-30"},
        format="json",
    )
    assert response.status_code == 400


def test_tax_refund_upstream_failure(fonepay_settings, order):
    _paid_fonepay_order(order)
    client = APIClient()
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{TAX_REFUND_PATH}", status_code=500
        )
        response = client.post(
            "/api/payments/fonepay/refund/",
            {"order_id": str(order.id), "invoice_number": "INV-1", "invoice_date": "2026-08-30"},
            format="json",
        )
    assert response.status_code == 502
