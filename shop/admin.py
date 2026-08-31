from django.contrib import admin

from .models import (
    BlogPost, Cart, CartItem, Category, Order, OrderItem, Product,
    ProductImage, ProductVariant, Review, Wishlist,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "base_price", "is_featured", "is_best_seller", "created_at")
    list_filter = ("category", "is_featured", "is_best_seller")
    search_fields = ("name", "sku_prefix")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = [ProductImageInline, ProductVariantInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("__str__", "sku", "resolved_price", "stock_quantity", "is_in_stock")
    list_filter = ("product__category",)
    search_fields = ("sku", "qr_code_reference", "product__name")
    actions = ["restock_selected"]

    @admin.action(description="Restock selected variants (set stock to 50)")
    def restock_selected(self, request, queryset):
        queryset.update(stock_quantity=50)


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("user",)
    filter_horizontal = ("variants",)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("__str__", "item_count", "total", "updated")
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "customer_name", "email", "payment_method", "status", "is_paid", "total", "gateway_reference", "payment_status", "created_at")
    list_filter = ("status", "payment_method", "is_paid")
    search_fields = ("customer_name", "contact_info", "email", "id")
    readonly_fields = ("id", "created_at", "updated_at", "gateway_reference", "payment_status")
    inlines = [OrderItemInline]
    actions = ["mark_confirmed", "mark_fulfilled", "mark_paid"]

    @admin.action(description="Mark selected orders as Confirmed")
    def mark_confirmed(self, request, queryset):
        queryset.filter(status="pending").update(status="confirmed")

    @admin.action(description="Mark selected orders as Fulfilled")
    def mark_fulfilled(self, request, queryset):
        queryset.filter(status="confirmed").update(status="fulfilled")

    @admin.action(description="Mark selected orders as Paid")
    def mark_paid(self, request, queryset):
        from .services.email import send_payment_emails
        for order in queryset.filter(is_paid=False):
            order.is_paid = True
            order.payment_status = "completed"
            order.save(update_fields=["is_paid", "payment_status"])
            send_payment_emails(order)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "reviewer_name", "rating", "created_at")
    list_filter = ("rating",)
    search_fields = ("reviewer_name", "product__name")


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "published_at")
    prepopulated_fields = {"slug": ("title",)}
