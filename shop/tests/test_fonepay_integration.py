import pytest
import requests_mock
from rest_framework.test import APIClient

from shop.payments.fonepay import GENERATE_QR_PATH, STATUS_PATH

pytestmark = pytest.mark.django_db


def test_full_fonepay_journey(fonepay_settings, order):
    client = APIClient()
    with requests_mock.Mocker() as m:
        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{GENERATE_QR_PATH}",
            json={"qrMessage": "QR-PAYLOAD"},
        )
        qr_resp = client.post(
            "/api/payments/fonepay/qr/",
            {"order_id": str(order.id)},
            format="json",
        )
        assert qr_resp.status_code == 200
        prn = qr_resp.json()["prn"]

        m.post(
            f"{fonepay_settings.FONEPAY_BASE_URL}{STATUS_PATH}",
            json={"prn": prn, "paymentStatus": "COMPLETED", "fonepayTraceId": "trace-42"},
        )
        status_resp = client.post(
            "/api/payments/fonepay/status/",
            {"prn": prn},
            format="json",
        )

    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["is_paid"] is True
    assert body["order_status"] == "confirmed"
    assert body["gateway_reference"] == "trace-42"

    order.refresh_from_db()
    assert order.is_paid is True
    assert order.status == "confirmed"
    assert order.gateway_reference == "trace-42"
    assert order.prn == prn
