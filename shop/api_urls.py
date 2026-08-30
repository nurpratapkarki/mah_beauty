from rest_framework.routers import DefaultRouter

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

urlpatterns = router.urls
