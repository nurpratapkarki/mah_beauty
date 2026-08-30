from decimal import Decimal

import pytest
import requests_mock
from rest_framework.test import APIClient

from shop.models import Order, PaymentMethod
from shop.payments.fonepay import GENERATE_QR_PATH

pytestmark = pytest.mark.django_db


def test_generate_qr_success(fonepay_settings, order):
    client = APIClient()
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{GENERATE_QR_PATH}",
            json={"qrMessage": "0002010102...fonepay", "message": "QR generated", "success": True},
        )
        response = client.post(
            "/api/payments/fonepay/qr/",
            {"order_id": str(order.id)},
            format="json",
        )

    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == str(order.id)
    assert body["prn"]
    assert body["amount"] == "1500.00"
    assert body["qr"] == "0002010102...fonepay"

    order.refresh_from_db()
    assert order.prn == body["prn"]
    assert order.payment_status == "pending"
    assert order.is_paid is False


@pytest.mark.parametrize(
    ("kwargs", "status_code"),
    [
        ({"payment_method": PaymentMethod.COD}, 400),
        ({"is_paid": True}, 400),
    ],
)
def test_generate_qr_rejects_invalid_order(fonepay_settings, order, kwargs, status_code):
    Order.objects.filter(pk=order.pk).update(**kwargs)
    existing_prn = order.prn
    client = APIClient()
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{GENERATE_QR_PATH}",
            json={"qrMessage": "qr"},
        )
        response = client.post(
            "/api/payments/fonepay/qr/",
            {"order_id": str(order.id)},
            format="json",
        )
    assert response.status_code == status_code
    order.refresh_from_db()
    assert order.prn == existing_prn


def test_generate_qr_order_not_found(fonepay_settings, order):
    client = APIClient()
    response = client.post(
        "/api/payments/fonepay/qr/",
        {"order_id": "00000000-0000-0000-0000-000000000000"},
        format="json",
    )
    assert response.status_code == 404


def test_generate_qr_upstream_failure_leaves_order_safe(fonepay_settings, order):
    client = APIClient()
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{GENERATE_QR_PATH}",
            status_code=500,
        )
        response = client.post(
            "/api/payments/fonepay/qr/",
            {"order_id": str(order.id)},
            format="json",
        )
    assert response.status_code == 502
    order.refresh_from_db()
    assert order.is_paid is False
    assert order.status == "pending"
    assert order.payment_status in ("", "failed")


def test_generate_qr_zero_total_rejected(fonepay_settings, order):
    Order.objects.filter(pk=order.pk).update(total=Decimal("0.00"))
    client = APIClient()
    response = client.post(
        "/api/payments/fonepay/qr/",
        {"order_id": str(order.id)},
        format="json",
    )
    assert response.status_code == 400


def test_generate_qr_with_tax_refund(fonepay_settings):
    from shop.payments.fonepay import FonepayClient, _hmac_sha512

    client = FonepayClient()
    captured = {}
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{GENERATE_QR_PATH}",
            additional_matcher=lambda req: captured.update(req.json()) or True,
            json={"qrMessage": "TAX-QR"},
        )
        result = client.generate_qr(
            amount="16.00",
            prn="PRN-TAX",
            remarks1="r1",
            remarks2="r2",
            tax_amount="1.00",
            tax_refund="true",
        )

    assert result["qr"] == "TAX-QR"
    assert captured["taxAmount"] == "1.00"
    assert captured["taxRefund"] == "true"
    expected_msg = "16.00,PRN-TAX,{mc},r1,r2,1.00,true".format(
        mc=fonepay_settings.FONEPAY_MERCHANT_CODE
    )
    assert captured["dataValidation"] == _hmac_sha512(
        fonepay_settings.FONEPAY_SECRET_KEY, expected_msg
    )


def test_generate_qr_without_tax_refund_no_tax_fields(fonepay_settings):
    from shop.payments.fonepay import FonepayClient

    client = FonepayClient()
    captured = {}
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{GENERATE_QR_PATH}",
            additional_matcher=lambda req: captured.update(req.json()) or True,
            json={"qrMessage": "QR"},
        )
        client.generate_qr(amount="16.00", prn="PRN", remarks1="r1")

    assert "taxAmount" not in captured
    assert "taxRefund" not in captured
