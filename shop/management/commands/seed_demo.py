"""Seed the shop with realistic demo data using Faker.

Creates categories, products (with variants + brand gallery images), reviews,
blog posts, and optionally users, wishlists, carts and orders — all matching
the shapes the Mah Beauty frontend consumes.

Usage::

    python manage.py seed_demo
    python manage.py seed_demo --products 12 --reviews 40 --blog 6
    python manage.py seed_demo --users 5 --orders 10
    python manage.py seed_demo --flush            # clear shop data first

Images are generated as pastel placeholder JPEGs under ``media/``.
"""

from decimal import Decimal
from io import BytesIO
from random import randint

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from PIL import Image, ImageDraw

from shop.models import (
    BlogPost,
    Cart,
    CartItem,
    Category,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    Wishlist,
)

try:
    from faker import Faker
except ImportError:  # pragma: no cover
    raise CommandError(
        "The 'Faker' package is required for seed_demo. "
        "Install it with: pip install Faker"
    )

User = get_user_model()

# Fixed demo categories (slugs / names match the frontend shop-by-category).
CATEGORIES = [
    {"name": "Lips", "slug": "lips"},
    {"name": "Skin", "slug": "skin"},
    {"name": "Eyes", "slug": "eyes"},
]

# Reasonable defaults when options aren't supplied.
DEFAULT_PRODUCTS = 8
DEFAULT_VARIANTS_MIN = 2
DEFAULT_VARIANTS_MAX = 4
DEFAULT_REVIEWS = 24
DEFAULT_BLOG = 4
DEFAULT_USERS = 0
DEFAULT_ORDERS = 0

# Shade-name seeds so variants look like a makeup brand rather than lorem.
SHADE_SEEDS = [
    "Petal Nude",
    "Rose Mah",
    "Dusty Rose",
    "Apricot",
    "Champagne",
    "Peach Glow",
    "Clear",
    "Soft Black",
    "Warm Brown",
    "Rose Gold",
    "Deep Burgundy",
    "Shade 01 - Porcelain",
    "Shade 02 - Light",
    "Shade 05 - Medium",
    "Shade 08 - Deep",
    "Honey",
    "Mauve",
    "Terra",
    "Caramel",
    "Blush",
    "Bronze",
    "Ivory",
    "Sand",
    "Cocoa",
]

_PRODUCT_TYPES = (
    "Lipstick",
    "Lip Oil",
    "Cream Blush",
    "Serum Foundation",
    "Liquid Liner",
    "Highlighter",
    "Mascara",
    "Face Primer",
)

_WORDS = (
    "velvet", "glass", "soft", "glow", "fine", "dew", "rose", "bloom", "flush",
    "silk", "serum", "velour", "satin", "luminous", "sheer", "petal", "golden",
)

_CITIES = ("Kathmandu", "Lalitpur", "Pokhara", "Biratnagar", "Butwal", "Bhaktapur")


class Command(BaseCommand):
    help = "Seed the shop with Faker-generated demo data matching the frontend schema."

    def add_arguments(self, parser):
        parser.add_argument(
            "--products", type=int, default=DEFAULT_PRODUCTS,
            help="Number of products to create (default %(default)s).",
        )
        parser.add_argument(
            "--reviews", type=int, default=DEFAULT_REVIEWS,
            help="Number of reviews to create (default %(default)s).",
        )
        parser.add_argument(
            "--blog", type=int, default=DEFAULT_BLOG,
            help="Number of blog posts to create (default %(default)s).",
        )
        parser.add_argument(
            "--users", type=int, default=DEFAULT_USERS,
            help="Number of customer accounts to create (default %(default)s).",
        )
        parser.add_argument(
            "--orders", type=int, default=DEFAULT_ORDERS,
            help="Number of orders to create (default %(default)s).",
        )
        parser.add_argument(
            "--flush", action="store_true",
            help="Delete existing shop seed data before creating new rows.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        fake = Faker()

        if options["flush"]:
            self._flush()

        categories = self._create_categories()
        products = self._create_products(fake, categories, options["products"])
        variants = [v for p in products for v in p.variants.all()]
        self._create_reviews(fake, products, options["reviews"])
        self._create_blog_posts(fake, options["blog"])
        users = self._create_users(fake, options["users"])
        if variants and users:
            self._create_carts_and_wishlists(fake, users, variants)
        if variants and options["orders"]:
            self._create_orders(
                fake, variants, users, options["orders"],
            )

        self.stdout.write(self.style.SUCCESS(
            f"Done: {len(categories)} categories, {len(products)} products, "
            f"{len(variants)} variants, {options['reviews']} reviews, "
            f"{options['blog']} blog posts, {options['users']} users, "
            f"{options['orders']} orders."
        ))

    # ── data creation ──────────────────────────────────────────────────────

    def _flush(self):
        for model in (
            Wishlist, CartItem, Cart, OrderItem, Order,
            Review, ProductImage, ProductVariant, Product,
            BlogPost, Category,
        ):
            model.objects.all().delete()
        self.stdout.write("Flushed existing shop data.")

    def _create_categories(self):
        cats = []
        for data in CATEGORIES:
            cat, _ = Category.objects.get_or_create(
                slug=data["slug"], defaults={"name": data["name"]},
            )
            cats.append(cat)
        return cats

    def _create_products(self, fake, categories, count):
        products = []
        for i in range(count):
            name = self._faker_product_name(fake)
            slug = self._unique_slug(Product, f"{name} {i + 1}")
            product = Product.objects.create(
                name=name,
                slug=slug,
                description="\n\n".join(fake.paragraphs(nb=2)),
                base_price=fake.pydecimal(
                    left_digits=2, right_digits=2, positive=True,
                    min_value=5, max_value=65,
                ),
                category=fake.random_element(categories),
                sku_prefix=slugify(name).upper()[:10][:20],
                short_descriptor=fake.catch_phrase()[:150],
                is_featured=fake.boolean(chance_of_getting_true=35),
                is_best_seller=fake.boolean(chance_of_getting_true=35),
            )
            self._create_variants(
                fake, product,
                fake.random_int(DEFAULT_VARIANTS_MIN, DEFAULT_VARIANTS_MAX),
            )
            self._create_brand_images(fake, product)
            products.append(product)
        return products

    def _faker_product_name(self, fake):
        words = fake.random_elements(
            elements=_WORDS, length=fake.random_int(2, 3), unique=True,
        )
        return (
            " ".join(w.title() for w in words)
            + " "
            + fake.random_element(_PRODUCT_TYPES)
        )

    def _create_variants(self, fake, product, count):
        shades = fake.random_elements(
            elements=SHADE_SEEDS, length=count, unique=True,
        )
        for j, shade in enumerate(shades, start=1):
            price = None
            if fake.boolean(chance_of_getting_true=25):
                price = product.base_price + fake.pydecimal(
                    left_digits=1, right_digits=2, positive=True,
                    min_value=1, max_value=9,
                )
            sku = f"{product.sku_prefix}-{j:03d}"
            ProductVariant.objects.create(
                product=product,
                shade_or_size=shade,
                sku=sku,
                price=price,
                stock_quantity=fake.random_int(0, 60),
                qr_code_reference=f"{sku}-QR",
                variant_image=self._placeholder_image(f"variant-{product.slug}-{j}"),
            )

    def _create_brand_images(self, fake, product):
        count = fake.random_int(1, 3)
        for k in range(count):
            ProductImage.objects.create(
                product=product,
                image=self._placeholder_image(f"brand-{product.slug}-{k}"),
                ordering=k,
            )

    def _create_reviews(self, fake, products, count):
        for _ in range(count):
            Review.objects.create(
                product=fake.random_element(products),
                reviewer_name=fake.name(),
                rating=fake.random_int(3, 5),
                review_text=" ".join(fake.sentences(nb=fake.random_int(2, 4))),
                created_at=fake.date_time_this_year(before_now=True),
            )

    def _create_blog_posts(self, fake, count):
        for i in range(count):
            title = fake.sentence(nb_words=5).rstrip(".").title()
            slug = self._unique_slug(BlogPost, f"{slugify(title)} {i + 1}")
            BlogPost.objects.create(
                slug=slug,
                title=title,
                excerpt=fake.sentence(nb_words=14)[:300],
                content="\n\n".join(fake.paragraphs(nb=3)),
                cover_image=self._placeholder_image(f"blog-{slug}"),
                published_at=fake.date_time_this_year(before_now=True),
            )

    def _create_users(self, fake, count):
        users = []
        for _ in range(count):
            name = fake.name().split()
            first = name[0]
            last = " ".join(name[1:]) if len(name) > 1 else ""
            email = fake.unique.email()
            username = slugify(email.split("@")[0]) or f"user{fake.random_int(100, 999)}"
            if User.objects.filter(username=username).exists():
                username = f"{username}{fake.random_int(10, 999)}"
            users.append(
                User.objects.create_user(
                    username=username,
                    email=email,
                    password="testpass123",
                    first_name=first,
                    last_name=last,
                )
            )
        return users

    def _create_carts_and_wishlists(self, fake, users, variants):
        for user in users:
            wishlist, _ = Wishlist.objects.get_or_create(user=user)
            wishlist.variants.set(
                fake.random_elements(
                    elements=variants, length=fake.random_int(1, 3), unique=True,
                )
            )

            cart, _ = Cart.objects.get_or_create(user=user)
            for variant in fake.random_elements(
                elements=variants, length=fake.random_int(1, 4), unique=True,
            ):
                CartItem.objects.get_or_create(
                    cart=cart, variant=variant,
                    defaults={"quantity": fake.random_int(1, 3)},
                )

    def _create_orders(self, fake, variants, users, count):
        """Create orders + items. OrderItem post-save signals decrement stock
        and fire emails (console backend in dev) — both safe to keep on.

        Only in-stock variants are picked, and each line's quantity is clamped
        to the stock that's actually available, so the stock-decrement signal
        never raises."""
        in_stock = [v for v in variants if v.stock_quantity > 0]
        if not in_stock:
            self.stdout.write("Skipping orders — no variants in stock.")
            return
        for _ in range(count):
            user = fake.random_element(users) if users else None
            picked = fake.random_elements(
                elements=in_stock, length=fake.random_int(1, min(4, len(in_stock))),
                unique=True,
            )
            items = []
            total = Decimal("0")
            for variant in picked:
                qty = fake.random_int(
                    1, min(3, variant.stock_quantity),
                )
                price = variant.resolved_price
                total += price * qty
                items.append((variant, qty, price))

            order = Order.objects.create(
                user=user,
                customer_name=fake.name(),
                contact_info=fake.phone_number()[:150],
                email=fake.unique.email() if user is None else user.email,
                shipping_address_line=fake.street_address()[:255],
                shipping_city=fake.random_element(_CITIES),
                shipping_landmark=fake.random_element(
                    ("Near the old temple", "Opposite the supermarket", "")
                )[:255],
                total=total,
                payment_method=fake.random_element(
                    [PaymentMethod.COD, PaymentMethod.WHATSAPP, PaymentMethod.INSTAGRAM]
                ),
                status=fake.random_element([s.value for s in OrderStatus]),
            )
            for variant, qty, price in items:
                OrderItem.objects.create(
                    order=order, variant=variant, quantity=qty, price=price,
                )

    # ── helpers ────────────────────────────────────────────────────────────

    def _unique_slug(self, model, base):
        slug = slugify(base) or "item"
        qs = model.objects.filter(slug=slug)
        counter = 2
        while qs.exists():
            slug = f"{slugify(base)}-{counter}"
            counter += 1
        return slug

    def _placeholder_image(self, label):
        """Return a ContentFile holding a pastel placeholder JPEG, ready to
        assign to an ImageField."""
        rgba = (randint(240, 255), randint(235, 250), randint(240, 255))
        size = (800, 800)
        img = Image.new("RGB", size, rgba)
        draw = ImageDraw.Draw(img)
        draw.ellipse(
            (size[0] // 4, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4),
            fill=(rgba[0] - 30, rgba[1] - 25, rgba[2] - 20),
        )
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return ContentFile(buf.getvalue(), name=f"{slugify(label)}.jpg")
