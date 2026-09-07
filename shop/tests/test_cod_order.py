import pytest
from decimal import Decimal

from rest_framework.test import APIClient

from shop.models import Order, PaymentMethod

pytestmark = pytest.mark.django_db


def test_create_order_with_cod(variant):
    client = APIClient()
    response = client.post(
        "/api/orders/",
        {
            "customer_name": "Jane Doe",
            "contact_info": "9841000000",
            "shipping_address_line": "Kumaripati",
            "shipping_city": "Lalitpur",
            "total": "1500.00",
            "payment_method": "cod",
            "items": [
                {"variant": variant.id, "quantity": 1, "price": "1500.00"},
            ],
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["payment_method"] == "cod"
    assert body["is_gateway_payment"] is False
    assert body["is_paid"] is False
    assert len(body["items"]) == 1
    assert body["items"][0]["variant"] == variant.id
    assert Order.objects.get(id=body["id"]).items.count() == 1


def test_cod_order_is_not_gateway_payment(variant):
    order = Order.objects.create(
        customer_name="Jane Doe",
        contact_info="9841000000",
        shipping_address_line="Kumaripati",
        shipping_city="Lalitpur",
        total=Decimal("1500.00"),
        payment_method=PaymentMethod.COD,
    )
    assert order.is_gateway_payment is False
    assert order.payment_method == "cod"
