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
        payment_method=PaymentMethod.FONEPAY,
    )
    OrderItem.objects.create(order=order, variant=variant, quantity=1, price=Decimal("1500.00"))
    return order


@pytest.fixture
def fonepay_settings(settings):
    settings.FONEPAY_USERNAME = "testuser"
    settings.FONEPAY_PASSWORD = "testpass"
    settings.FONEPAY_MERCHANT_CODE = "MERCH01"
    settings.FONEPAY_SECRET_KEY = "testsecret"
    settings.FONEPAY_BASE_URL = "https://fonepay.test"
    settings.FONEPAY_SANDBOX = True
    return settings
