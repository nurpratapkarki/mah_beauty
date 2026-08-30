# Mah Beauty — Django Backend

API-only Django backend (DRF + Jazzmin admin) for the Mah Beauty e-commerce frontend.
Built to match the frontend's TypeScript schema exactly so the Lovable frontend can be
pointed at these endpoints without reshaping components.

## Django Version

Requires Django 5.2 or newer (tested against 6.1, the current release as of August 2026).
The original scaffold pinned `Django>=4.2,<5.0`, which is now behind DRF's own supported
range — DRF has dropped support for Django 4.2, 5.0, and 5.1. The floor was raised to 5.2
(Django's LTS line, supported into 2028) rather than pinning to the newest short-term release,
for a more stable target on a small production backend. Verified clean against Django 6.1:
`manage.py check`, `makemigrations`, and `migrate` all run with no errors or deprecation warnings.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py createsuperuser
python3 manage.py runserver
```

Admin panel: `/admin/`
API root: `/api/`

## Models

- **Category** — name, slug (lips / skin / eyes)
- **Product** — name, slug, description, base_price, category, sku_prefix, short_descriptor, is_featured, is_best_seller
- **ProductImage** — brand-level gallery images for a product (replaces the frontend's `brand_images: string[]`)
- **ProductVariant** — shade/size, sku, price (nullable override of base_price), stock_quantity, qr_code_reference, variant_image
- **Wishlist** — one per user, many-to-many to ProductVariant
- **Cart / CartItem** — supports both logged-in users and guest sessions via `session_key`
- **Order / OrderItem** — guest checkout supported (`user` is nullable); see Payment Integration below
- **Review** — belongs to Product (not variant), so all shade/size reviews stack together
- **BlogPost** — slug, title, excerpt, content, cover_image, published_at

## API Endpoints

| Endpoint | Notes |
|---|---|
| `/api/categories/` | standard CRUD |
| `/api/products/` | filter by `category`, `is_featured`, `is_best_seller`; search by name/description; extra actions: `featured/`, `best_sellers/` |
| `/api/variants/` | filter by `product`; search by sku/qr/shade; extra action: `in_stock/` |
| `/api/wishlists/` | extra action: `mine/` (GET current user's wishlist, POST to add a variant) |
| `/api/carts/` | extra actions: `mine/` (resolve current user or guest cart), `add_item/`, `remove_item/` |
| `/api/orders/` | guest checkout allowed; extra actions: `cancel/`, `my_orders/` (authenticated) |
| `/api/reviews/` | filter by `product` |
| `/api/blog/` | lookup by `slug` instead of id |

## Payment Integration — left open by design

Per the current plan, real payment gateway integration (eSewa / Khalti) is **not wired up yet**,
pending business permissions. The schema was built so this can be switched on later with no
migration required:

- `Order.payment_method` already includes `esewa` and `khalti` as valid choices, alongside the
  currently "live" `whatsapp` and `instagram` methods — the frontend can show eSewa/Khalti as
  disabled/"Coming Soon" options today.
- `Order.gateway_reference` (blank by default) is reserved for the provider's transaction/payment
  ID once a gateway is integrated.
- `Order.is_paid` (defaults to `False`) is manually set via the admin action **"Mark selected
  orders as Paid"** for WhatsApp/Instagram orders today. Once gateway integration is live, this
  should instead be set automatically from the gateway's payment-confirmation webhook/callback.
- `Order.is_gateway_payment` is a read-only computed property so the frontend/API consumer can
  tell at a glance whether an order used (or will use) a gateway vs. a manual channel.

When you're ready to integrate eSewa/Khalti: add a webhook endpoint that verifies the provider's
signature, sets `gateway_reference` and `is_paid=True`, and transitions `status` to `confirmed`.
No changes to existing fields are needed.

## Other Assumptions

- Stock lives on `ProductVariant`, not `Product` — a product can be "in stock" if any variant has
  stock, exposed via `Product.is_in_stock` and `Product.price_from` (lowest variant price).
- Stock auto-decrements via a `post_save` signal on `OrderItem` creation.
- `Order.status` uses three values only (`pending`, `confirmed`, `fulfilled`), matching the
  agreed business flow — not the e-commerce feature pack's default five-status flow.
- `Order.cancel()` restores stock for all items and resets status to `pending` for shop-owner
  re-review, rather than a `cancelled` status (none was requested).
- `ShippingAddress` was flattened into three fields directly on `Order` (`shipping_address_line`,
  `shipping_city`, `shipping_landmark`) rather than a separate model, since it's only ever used
  in that one place.
- Django's built-in `User` model is used via `settings.AUTH_USER_MODEL` rather than a custom
  User model, since the frontend's `User` type (id/name/email) maps cleanly onto it.
- Guest carts are supported via `Cart.session_key`; deciding how that key is generated/persisted
  (Django sessions vs. a custom frontend-generated token) is left to the integration step.

## Confirmed DSL

```
[project: mah_beauty]
[app: shop]
[ui: api_only]

Category: name(str,max=100) slug(slug)
Product: name(str,max=200) slug(slug) description(text) base_price(decimal,max=10,dec=2) category(FK:Category) sku_prefix(str,max=20) short_descriptor(str,max=150,blank) is_featured(bool,default=False) is_best_seller(bool,default=False)
ProductImage: product(FK:Product,related=brand_images) image(image) ordering(int,default=0)
ProductVariant: product(FK:Product,related=variants) shade_or_size(str,max=100) sku(str,unique,max=50) price(decimal,max=10,dec=2,blank) stock_quantity(int,default=0) qr_code_reference(str,unique,max=100) variant_image(image)
Wishlist: user(O2O:User) variants(M2M:ProductVariant)
Cart: user(O2O:User,null) session_key(str,blank,max=100)
CartItem: cart(FK:Cart,related=items) variant(FK:ProductVariant) quantity(int,default=1)
Order: user(FK:User,null) customer_name(str,max=150) contact_info(str,max=150) shipping_address_line(str,max=255) shipping_city(str,max=100) shipping_landmark(str,max=255,blank) total(decimal,max=10,dec=2) payment_method(choice:esewa,khalti,whatsapp,instagram) status(choice:pending,confirmed,fulfilled) created_at(auto)
OrderItem: order(FK:Order,related=items) variant(FK:ProductVariant) quantity(int) price(decimal,max=10,dec=2)
Review: product(FK:Product,related=reviews) reviewer_name(str,max=150) rating(int) review_text(text) created_at(auto)
BlogPost: slug(slug) title(str,max=200) excerpt(str,max=300) content(text) cover_image(image) published_at(datetime)
```
