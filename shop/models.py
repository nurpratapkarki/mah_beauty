import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products")
    sku_prefix = models.CharField(max_length=20)
    short_descriptor = models.CharField(max_length=150, blank=True)
    is_featured = models.BooleanField(default=False)
    is_best_seller = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("shop:product-detail", kwargs={"pk": self.pk})

    @property
    def price_from(self):
        """Lowest sellable price across all variants, falling back to base_price."""
        prices = [v.resolved_price for v in self.variants.all()]
        return min(prices) if prices else self.base_price

    @property
    def is_in_stock(self):
        return any(v.stock_quantity > 0 for v in self.variants.all())


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="brand_images")
    image = models.ImageField(upload_to="products/brand/")
    ordering = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordering"]

    def __str__(self):
        return f"{self.product.name} image #{self.ordering}"


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    shade_or_size = models.CharField(max_length=100)
    sku = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Overrides product.base_price when set.",
    )
    stock_quantity = models.PositiveIntegerField(default=0)
    qr_code_reference = models.CharField(max_length=100, unique=True)
    variant_image = models.ImageField(upload_to="products/variants/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product", "shade_or_size"]

    def __str__(self):
        return f"{self.product.name} — {self.shade_or_size}"

    @property
    def resolved_price(self):
        """Single source of truth for price fallback — mirrors the frontend's
        variantPrice() helper so backend and frontend never drift."""
        return self.price if self.price is not None else self.product.base_price

    @property
    def is_in_stock(self):
        return self.stock_quantity > 0

    def decrement_stock(self, qty):
        if self.stock_quantity < qty:
            raise ValueError(
                f"Insufficient stock for '{self}'. Available: {self.stock_quantity}"
            )
        self.stock_quantity -= qty
        self.save(update_fields=["stock_quantity"])

    def increment_stock(self, qty):
        self.stock_quantity += qty
        self.save(update_fields=["stock_quantity"])


class Wishlist(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist")
    variants = models.ManyToManyField(ProductVariant, related_name="wishlisted_by", blank=True)

    def __str__(self):
        return f"Wishlist({self.user})"


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="cart", null=True, blank=True,
    )
    session_key = models.CharField(max_length=100, blank=True)  # guest cart support
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart({self.user or self.session_key or self.pk})"

    @property
    def total(self):
        return sum((item.line_total for item in self.items.select_related("variant")), 0)

    @property
    def item_count(self):
        return self.items.count()


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cart", "variant")

    def __str__(self):
        return f"{self.variant} x{self.quantity}"

    @property
    def line_total(self):
        return self.variant.resolved_price * self.quantity


class PaymentMethod(models.TextChoices):
    COD = "cod", "Cash on Delivery"
    ESEWA = "esewa", "eSewa"
    KHALTI = "khalti", "Khalti"
    WHATSAPP = "whatsapp", "WhatsApp"
    INSTAGRAM = "instagram", "Instagram"


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    FULFILLED = "fulfilled", "Fulfilled"


class Order(models.Model):
    """
    payment_method currently only WhatsApp/Instagram are "live" — eSewa and Khalti
    exist as selectable values so the frontend can show them (disabled/"coming soon")
    without a future schema change. When gateway integration is switched on:
      - start populating gateway_reference with the provider's transaction/payment ID
      - is_gateway_payment / is_paid can drive real payment-confirmed logic
      - no migration needed beyond possibly making gateway_reference required
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="orders", null=True, blank=True,
    )
    customer_name = models.CharField(max_length=150)
    contact_info = models.CharField(max_length=150)  # phone, email, or social handle
    email = models.EmailField(
        max_length=254, blank=True,
        help_text="Customer email for order and payment confirmation emails.",
    )

    shipping_address_line = models.CharField(max_length=255)
    shipping_city = models.CharField(max_length=100)
    shipping_landmark = models.CharField(max_length=255, blank=True)

    total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)

    # --- forward-compatible payment gateway fields (populated once gateway integration is live) ---
    gateway_reference = models.CharField(
        max_length=100, blank=True,
        help_text="Transaction/payment ID from the payment gateway (e.g. eSewa transaction_code).",
    )
    is_paid = models.BooleanField(
        default=False,
        help_text="Manually confirmed for COD/WhatsApp/Instagram orders; set automatically for gateway payments.",
    )

    # --- gateway tracking fields ---
    transaction_uuid = models.CharField(
        max_length=50, blank=True,
        help_text="Unique transaction identifier for gateway payments (e.g. eSewa transaction_uuid).",
    )
    payment_status = models.CharField(
        max_length=20, blank=True,
        help_text="Last known gateway payment status (pending, COMPLETED, failed).",
    )

    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.id} — {self.customer_name}"

    @property
    def is_gateway_payment(self):
        return self.payment_method in (
            PaymentMethod.ESEWA,
            PaymentMethod.KHALTI,
        )

    def can_cancel(self):
        return self.status in (OrderStatus.PENDING, OrderStatus.CONFIRMED)

    def cancel(self):
        if not self.can_cancel():
            raise ValueError("Only pending or confirmed orders can be cancelled.")
        for item in self.items.select_related("variant"):
            item.variant.increment_stock(item.quantity)
        self.status = OrderStatus.PENDING  # left as-is for shop owner to re-review; see README
        self.save(update_fields=["status"])

    def mark_gateway_confirmed(self, gateway_reference, status="COMPLETED"):
        """Confirm an order after a verified gateway payment. Idempotent — safe to call when
        the order is already confirmed/paid."""
        update_fields = ["is_paid", "payment_status", "status"]
        was_already_paid = self.is_paid
        self.is_paid = True
        self.payment_status = status
        self.status = OrderStatus.CONFIRMED
        if gateway_reference:
            self.gateway_reference = gateway_reference
            update_fields.append("gateway_reference")
        self.save(update_fields=update_fields)

        # Notify customer + admin of the successful payment (once).
        if not was_already_paid:
            from .services.email import send_payment_emails
            send_payment_emails(self)



class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)  # price at time of order

    def __str__(self):
        return f"{self.variant} x{self.quantity}"

    @property
    def line_total(self):
        return self.price * self.quantity


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    reviewer_name = models.CharField(max_length=150)
    rating = models.PositiveSmallIntegerField()  # 1-5
    review_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reviewer_name} — {self.rating}\u2605 on {self.product.name}"


class BlogPost(models.Model):
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    excerpt = models.CharField(max_length=300)
    content = models.TextField()
    cover_image = models.ImageField(upload_to="blog/")
    published_at = models.DateTimeField()

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title
