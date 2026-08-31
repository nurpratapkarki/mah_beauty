import pytest
from decimal import Decimal

from shop.models import Category, Order, OrderItem, PaymentMethod, Product, ProductVariant


@pytest.fixture
def seller():
    return Category.objects.create(name="Lips", slug="lips")


@pytest.fixture
def product(seller):
    return Product.objects.create(
        name="Lipstick",
        slug="lipstick",
        description="A nice lipstick",
        base_price=Decimal("1500.00"),
        category=seller,
        sku_prefix="LP",
    )


@pytest.fixture
def variant(product):
    return ProductVariant.objects.create(
        product=product,
        shade_or_size="Red",
        sku="LP-RED-1",
        stock_quantity=10,
        qr_code_reference="QR-1",
    )


@pytest.fixture
def order(variant):
    order = Order.objects.create(
        customer_name="Jane Doe",
        contact_info="9841000000",
        shipping_address_line="Kumaripati",
        shipping_city="Lalitpur",
        total=Decimal("1500.00"),
        payment_method=PaymentMethod.COD,
    )
    OrderItem.objects.create(order=order, variant=variant, quantity=1, price=Decimal("1500.00"))
    return order


@pytest.fixture
def esewa_order(variant):
    order = Order.objects.create(
        customer_name="Jane Doe",
        contact_info="9841000000",
        shipping_address_line="Kumaripati",
        shipping_city="Lalitpur",
        total=Decimal("1500.00"),
        payment_method=PaymentMethod.ESEWA,
    )
    OrderItem.objects.create(order=order, variant=variant, quantity=1, price=Decimal("1500.00"))
    return order


@pytest.fixture
def esewa_settings(settings):
    settings.ESEWA_MERCHANT_CODE = "EPAYTEST"
    settings.ESEWA_SECRET_KEY = "8gBm/:&EnhH.1/q"
    settings.ESEWA_SANDBOX = True
    settings.ESEWA_BASE_URL = ""
    settings.ESEWA_SUCCESS_URL = "http://localhost:8000/success"
    settings.ESEWA_FAILURE_URL = "http://localhost:8000/failure"
    return settings
