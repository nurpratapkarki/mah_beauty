from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import OrderItem
from .services.email import send_order_emails


@receiver(post_save, sender=OrderItem)
def decrement_stock_on_order_item_save(sender, instance, created, **kwargs):
    if created:
        instance.variant.decrement_stock(instance.quantity)


@receiver(post_save, sender=OrderItem)
def send_order_placed_emails(sender, instance, created, **kwargs):
    """Notify customer + admin once an order's first line item is added.

    Order lines are added after the Order row exists, so firing on the first
    OrderItem guarantees the email shows the full line items.
    """
    if not created:
        return
    order = instance.order
    if order.items.count() != 1:
        # Not the first line item — order may still be being assembled.
        return
    send_order_emails(order)
