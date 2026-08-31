import pytest
from decimal import Decimal

from rest_framework.test import APIClient

from shop.models import Cart, CartItem


@pytest.mark.django_db
def test_carts_list_avoids_nplus1(variant, django_assert_num_queries):
    """Listing carts must not fire N+1 queries for per-item price/total lookups.

    Variant prices are null (they fall back to product.base_price), the worst
    case: each line_total resolves variant.product. The view prefetch must keep
    the whole list at a constant query count regardless of cart/item totals.
    """
    from shop.models import ProductVariant

    second = ProductVariant.objects.create(
        product=variant.product,
        shade_or_size="Blue",
        sku="LP-BLUE-1",
        stock_quantity=5,
        qr_code_reference="QR-2",
    )

    for key in ("a", "b", "c"):
        cart = Cart.objects.create(session_key=key)
        CartItem.objects.create(cart=cart, variant=variant, quantity=2)
        CartItem.objects.create(cart=cart, variant=second, quantity=1)

    client = APIClient()
    # 1 pagination COUNT + 1 carts + 1 items + 1 variants-with-product.
    # Constant regardless of cart/item count — no per-item price lookups.
    with django_assert_num_queries(4):
        resp = client.get("/api/carts/")

    assert resp.status_code == 200
    results = resp.data["results"]
    assert len(results) == 3
    assert {c["item_count"] for c in results} == {2}
    assert all(Decimal(c["total"]) == Decimal("4500.00") for c in results)


@pytest.mark.django_db
def test_cart_mine_avoids_nplus1(variant, django_assert_num_queries):
    """A single cart with many null-price items must not N+1 on variant.product.

    ``mine`` reloads the cart through the prefetched queryset, so serializing
    many line items stays at a constant query count.
    """
    from django.contrib.auth import get_user_model
    from shop.models import ProductVariant

    extra = [
        ProductVariant.objects.create(
            product=variant.product,
            shade_or_size=f"Shade {i}",
            sku=f"LP-X-{i}",
            stock_quantity=5,
            qr_code_reference=f"QR-X-{i}",
        )
        for i in range(5)
    ]

    user = get_user_model().objects.create_user(
        email="cart@test.com", username="cart", password="x", phone_number="9800000000"
    )
    cart = Cart.objects.create(user=user)
    for v in [variant, *extra]:
        CartItem.objects.create(cart=cart, variant=v, quantity=1)

    client = APIClient()
    client.force_authenticate(user=user)
    # get_or_create lookup + reload + items + variants-with-product.
    with django_assert_num_queries(4):
        resp = client.get("/api/carts/mine/")

    assert resp.status_code == 200
    assert resp.data["item_count"] == 6
    assert Decimal(resp.data["total"]) == Decimal("9000.00")


@pytest.mark.django_db
def test_product_list_stays_constant(variant, django_assert_num_queries):
    """Product list must not N+1: variant.product resolution is prefetched.

    Variants carry null price, so every serialized variant falls back to
    product.base_price. The explicit Prefetch(select_related("product")) keeps
    this at a constant query count.
    """
    from shop.models import ProductVariant

    for i in range(4):
        ProductVariant.objects.create(
            product=variant.product,
            shade_or_size=f"Shade {i}",
            sku=f"LP-P-{i}",
            stock_quantity=5,
            qr_code_reference=f"QR-P-{i}",
        )

    client = APIClient()
    # 1 pagination COUNT + 1 products(+category) + 1 variants(+product) + brand_images.
    # Constant regardless of variant count.
    with django_assert_num_queries(4):
        resp = client.get("/api/products/")

    assert resp.status_code == 200
    assert len(resp.data["results"]) == 1
    variants = resp.data["results"][0]["variants"]
    assert len(variants) == 5
    assert all(Decimal(v["resolved_price"]) == Decimal("1500.00") for v in variants)
