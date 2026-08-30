from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import OrderItem


@receiver(post_save, sender=OrderItem)
def decrement_stock_on_order_item_save(sender, instance, created, **kwargs):
    if created:
        instance.variant.decrement_stock(instance.quantity)
