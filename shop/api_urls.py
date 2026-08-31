from django.urls import path
from rest_framework.routers import DefaultRouter

from .payments.views import esewa_callback, esewa_check_status, esewa_initiate
from .views import (
    BlogPostViewSet, CartViewSet, CategoryViewSet, OrderViewSet,
    ProductVariantViewSet, ProductViewSet, ReviewViewSet, WishlistViewSet,
)

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"products", ProductViewSet, basename="product")
router.register(r"variants", ProductVariantViewSet, basename="variant")
router.register(r"wishlists", WishlistViewSet, basename="wishlist")
router.register(r"carts", CartViewSet, basename="cart")
router.register(r"orders", OrderViewSet, basename="order")
router.register(r"reviews", ReviewViewSet, basename="review")
router.register(r"blog", BlogPostViewSet, basename="blogpost")

urlpatterns = router.urls + [
    path("payments/esewa/initiate/", esewa_initiate, name="esewa-initiate"),
    path("payments/esewa/callback/", esewa_callback, name="esewa-callback"),
    path("payments/esewa/status/", esewa_check_status, name="esewa-status"),
]

