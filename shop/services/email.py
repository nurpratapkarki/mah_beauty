"""Transactional email service for shop order & payment notifications.

Sending failures are logged, never raised — a broken mail backend must not
break order placement or payment confirmation. All emails are sent through
Django's configured ``EMAIL_BACKEND`` (console in dev, SMTP in production).
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _render(template_name, context):
    """Render an HTML email body plus a plain-text fallback."""
    html = render_to_string(f"email/{template_name}.html", context)
    text = render_to_string(f"email/{template_name}.txt", context)
    return html, text


def _send(to, subject, template_name, context):
    """Build and send a single multi-part email. Failures are logged only."""
    try:
        if not to:
            logger.warning("Skipping email %r — no recipient", subject)
            return False
        html, text = _render(template_name, context)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to],
        )
        msg.attach_alternative(html, "text/html")
        msg.send()
        logger.info("Email sent to %s: %r", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email %r to %s", subject, to)
        return False


def _order_context(order):
    """Build a shared context dict for order-related email templates."""
    items = list(order.items.select_related("variant__product"))
    return {
        "order": order,
        "items": items,
        "total": order.total,
        "payment_method": order.get_payment_method_display(),
        "site_name": "mah_beauty",
    }


def send_order_confirmation_email(order):
    """Notify the customer that their order has been placed."""
    if not order.email:
        logger.info(
            "Skipping order confirmation email for order %s — no customer email", order.id
        )
        return False
    return _send(
        to=order.email,
        subject=f"Order Confirmation #{order.id}",
        template_name="order_confirmation",
        context=_order_context(order),
    )


def send_new_order_admin_email(order):
    """Notify the admin that a new order has been placed."""
    admin_email = getattr(settings, "ADMIN_EMAIL", "") or ""
    if not admin_email:
        logger.info(
            "Skipping new-order admin email for order %s — ADMIN_EMAIL not set", order.id
        )
        return False
    return _send(
        to=admin_email,
        subject=f"New Order Placed #{order.id}",
        template_name="new_order_admin",
        context=_order_context(order),
    )


def send_payment_success_email(order):
    """Notify the customer that their payment succeeded."""
    if not order.email:
        logger.info(
            "Skipping payment success email for order %s — no customer email", order.id
        )
        return False
    return _send(
        to=order.email,
        subject=f"Payment Received #{order.id}",
        template_name="payment_success",
        context=_order_context(order),
    )


def send_payment_success_admin_email(order):
    """Notify the admin that an order has been paid for."""
    admin_email = getattr(settings, "ADMIN_EMAIL", "") or ""
    if not admin_email:
        logger.info(
            "Skipping payment-success admin email for order %s — ADMIN_EMAIL not set",
            order.id,
        )
        return False
    return _send(
        to=admin_email,
        subject=f"Payment Received for Order #{order.id}",
        template_name="payment_success_admin",
        context=_order_context(order),
    )


def send_order_emails(order):
    """Send all order-placed notifications (customer + admin)."""
    send_order_confirmation_email(order)
    send_new_order_admin_email(order)


def send_payment_emails(order):
    """Send all payment-success notifications (customer + admin)."""
    send_payment_success_email(order)
    send_payment_success_admin_email(order)
