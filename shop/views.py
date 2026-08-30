from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    BlogPost, Cart, CartItem, Category, Order, OrderItem, Product,
    ProductVariant, Review, Wishlist,
)
from .serializers import (
    BlogPostSerializer, CartItemSerializer, CartSerializer, CategorySerializer,
    OrderSerializer, ProductSerializer, ProductVariantSerializer,
    ReviewSerializer, WishlistSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category", "is_featured", "is_best_seller"]
    search_fields = ["name", "short_descriptor", "description"]

    def get_queryset(self):
        return (
            Product.objects.all()
            .select_related("category")
            .prefetch_related("variants", "brand_images")
        )

    @action(detail=False, methods=["get"])
    def featured(self, request):
        qs = self.get_queryset().filter(is_featured=True)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=False, methods=["get"])
    def best_sellers(self, request):
        qs = self.get_queryset().filter(is_best_seller=True)
        return Response(self.get_serializer(qs, many=True).data)


class ProductVariantViewSet(viewsets.ModelViewSet):
    serializer_class = ProductVariantSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["product"]
    search_fields = ["sku", "qr_code_reference", "shade_or_size"]

    def get_queryset(self):
        return ProductVariant.objects.all().select_related("product")

    @action(detail=False, methods=["get"])
    def in_stock(self, request):
        qs = self.get_queryset().filter(stock_quantity__gt=0)
        return Response(self.get_serializer(qs, many=True).data)


class WishlistViewSet(viewsets.ModelViewSet):
    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Wishlist.objects.filter(user=self.request.user).prefetch_related("variants")

    @action(detail=False, methods=["get", "post"])
    def mine(self, request):
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        if request.method == "POST":
            variant_id = request.data.get("variant")
            variant = get_object_or_404(ProductVariant, pk=variant_id)
            wishlist.variants.add(variant)
        return Response(self.get_serializer(wishlist).data)


class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Cart.objects.all().prefetch_related("items__variant")

    @action(detail=False, methods=["get"])
    def mine(self, request):
        """Resolves the current user's cart, or a guest cart by session_key query param."""
        if request.user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=request.user)
        else:
            session_key = request.query_params.get("session_key", "")
            cart, _ = Cart.objects.get_or_create(session_key=session_key, user=None)
        return Response(self.get_serializer(cart).data)

    @action(detail=True, methods=["post"])
    def add_item(self, request, pk=None):
        cart = self.get_object()
        variant = get_object_or_404(ProductVariant, pk=request.data.get("variant"))
        quantity = int(request.data.get("quantity", 1))
        item, created = CartItem.objects.get_or_create(cart=cart, variant=variant, defaults={"quantity": quantity})
        if not created:
            item.quantity += quantity
            item.save(update_fields=["quantity"])
        return Response(CartItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def remove_item(self, request, pk=None):
        cart = self.get_object()
        CartItem.objects.filter(cart=cart, variant_id=request.data.get("variant")).delete()
        return Response(self.get_serializer(cart).data)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.AllowAny]  # guest checkout is supported by design

    def get_queryset(self):
        return Order.objects.all().prefetch_related("items__variant")

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        try:
            order.cancel()
            return Response({"status": "cancelled"})
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def my_orders(self, request):
        qs = self.get_queryset().filter(user=request.user)
        return Response(self.get_serializer(qs, many=True).data)


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["product"]

    def get_queryset(self):
        return Review.objects.all().select_related("product")


class BlogPostViewSet(viewsets.ModelViewSet):
    queryset = BlogPost.objects.all()
    serializer_class = BlogPostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = "slug"
