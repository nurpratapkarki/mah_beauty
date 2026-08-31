import pytest
from decimal import Decimal
from django.core import mail

from shop.models import Order, OrderItem, PaymentMethod
from shop.services.email import (
    send_new_order_admin_email,
    send_order_confirmation_email,
    send_payment_success_admin_email,
    send_payment_success_email,
)


@pytest.fixture
def customer_email_order(variant):
    order = Order.objects.create(
        customer_name="Jane Doe",
        contact_info="9841000000",
        email="jane@example.com",
        shipping_address_line="Kumaripati",
        shipping_city="Lalitpur",
        total=Decimal("1500.00"),
        payment_method=PaymentMethod.COD,
    )
    OrderItem.objects.create(order=order, variant=variant, quantity=1, price=Decimal("1500.00"))
    return order


@pytest.fixture
def locmem(settings):
    """Point the default mailer at the locmem (outbox) backend for verification."""
    settings.MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            "OPTIONS": {},
        }
    }
    return settings


def _outbox():
    return mail.outbox


# ── Customer confirmation ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_order_confirmation_sent_to_customer(customer_email_order, locmem):
    assert send_order_confirmation_email(customer_email_order) is True
    email = _outbox()[-1]
    assert email.to == ["jane@example.com"]
    assert "Order Confirmation" in email.subject
    assert str(customer_email_order.id) in email.subject
    assert str(customer_email_order.total) in email.body or "1500.00" in email.body


@pytest.mark.django_db
def test_order_confirmation_supports_html(customer_email_order, locmem):
    send_order_confirmation_email(customer_email_order)
    email = _outbox()[-1]
    assert email.alternatives, "expected an HTML alternative part"
    html = email.alternatives[0][0]
    assert "Order Confirmation" in html
    assert "jane@example.com" not in html


@pytest.mark.django_db
def test_order_confirmation_skipped_without_email(order, locmem, settings):
    settings.ADMIN_EMAIL = ""
    _outbox().clear()  # drop the admin email the order-created signal already fired
    assert order.email == ""
    assert send_order_confirmation_email(order) is False
    assert len(_outbox()) == 0


# ── Admin notification ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_new_order_admin_sent(customer_email_order, locmem, settings):
    settings.ADMIN_EMAIL = "ops@example.com"
    assert send_new_order_admin_email(customer_email_order) is True
    email = _outbox()[-1]
    assert email.to == ["ops@example.com"]
    assert "New Order" in email.subject


@pytest.mark.django_db
def test_new_order_admin_skipped_without_admin_email(customer_email_order, locmem, settings):
    settings.ADMIN_EMAIL = ""
    _outbox().clear()  # drop the order-confirmation email the fixture already fired
    assert customer_email_order.email  # sanity: fixture has a customer email
    assert send_new_order_admin_email(customer_email_order) is False
    assert len(_outbox()) == 0


# ── Payment success ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_payment_success_sent_to_customer(customer_email_order, locmem):
    assert send_payment_success_email(customer_email_order) is True
    email = _outbox()[-1]
    assert email.to == ["jane@example.com"]
    assert "Payment Received" in email.subject


@pytest.mark.django_db
def test_payment_success_admin_sent(customer_email_order, locmem, settings):
    settings.ADMIN_EMAIL = "ops@example.com"
    assert send_payment_success_admin_email(customer_email_order) is True
    email = _outbox()[-1]
    assert email.to == ["ops@example.com"]
    assert "Payment Received" in email.subject


@pytest.mark.django_db
def test_payment_success_skipped_without_customer_email(order, locmem, settings):
    settings.ADMIN_EMAIL = ""
    _outbox().clear()  # drop the admin email the order-created signal already fired
    assert send_payment_success_email(order) is False
    assert len(_outbox()) == 0


# ── Signal-driven triggers ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_order_emails_fire_on_first_order_item(variant, locmem, settings):
    settings.ADMIN_EMAIL = "ops@example.com"
    order = Order.objects.create(
        customer_name="Jane Doe",
        contact_info="9841000000",
        email="jane@example.com",
        shipping_address_line="Kumaripati",
        shipping_city="Lalitpur",
        total=Decimal("1500.00"),
        payment_method=PaymentMethod.ESEWA,
    )
    assert len(_outbox()) == 0
    OrderItem.objects.create(order=order, variant=variant, quantity=1, price=Decimal("1500.00"))
    recipients = {addr for email in _outbox() for addr in email.to}
    assert recipients == {"jane@example.com", "ops@example.com"}


@pytest.mark.django_db
def test_payment_emails_fire_once_on_confirm(customer_email_order, locmem, settings):
    settings.ADMIN_EMAIL = "ops@example.com"
    _outbox().clear()  # drop the order-confirmation email the fixture already fired
    customer_email_order.mark_gateway_confirmed(gateway_reference="txn-1", status="COMPLETE")
    assert len(_outbox()) == 2  # customer + admin

    # Idempotent re-confirm must not fire duplicate emails.
    customer_email_order.mark_gateway_confirmed(gateway_reference="txn-1", status="COMPLETE")
    assert len(_outbox()) == 2
