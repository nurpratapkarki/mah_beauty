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
cp .env.example .env          # then fill in real values (see .env.example)
python3 manage.py migrate
python3 manage.py createsuperuser
python3 manage.py runserver
```

Environment is read from `.env` (see `.env.example`). Secrets live only in the gitignored
`.env`, never in versioned source.

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

| Endpoint                        | Notes                                                                                                                          |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `/api/categories/`              | standard CRUD                                                                                                                  |
| `/api/products/`                | filter by `category`, `is_featured`, `is_best_seller`; search by name/description; extra actions: `featured/`, `best_sellers/` |
| `/api/variants/`                | filter by `product`; search by sku/qr/shade; extra action: `in_stock/`                                                         |
| `/api/wishlists/`               | extra action: `mine/` (GET current user's wishlist, POST to add a variant)                                                     |
| `/api/carts/`                   | extra actions: `mine/` (resolve current user or guest cart), `add_item/`, `remove_item/`                                       |
| `/api/orders/`                  | guest checkout allowed; extra actions: `cancel/`, `my_orders/` (authenticated)                                                 |
| `/api/payments/esewa/initiate/` | `POST` — build the signed eSewa payment payload for an order (see Payment Integration)                                        |
| `/api/payments/esewa/callback/` | `GET` — confirm an order from the eSewa redirect callback                                                                      |
| `/api/payments/esewa/status/`   | `POST` — check eSewa transaction status and confirm an order (fallback to callback)                                            |
| `/api/reviews/`                 | filter by `product`                                                                                                            |
| `/api/blog/`                    | lookup by `slug` instead of id                                                                                                 |

## Payment Integration

The backend supports **eSewa** (live gateway, redirect-based) and **Cash on Delivery (COD)**, plus
the legacy manual channels (WhatsApp / Instagram). Khalti remains reserved (not wired).

### eSewa (redirect gateway)

`Order.payment_method` includes `esewa`. Config is read from `.env` (see `mah_beauty_project/
settings.py`); nothing secret lives in versioned code. Sandbox defaults are provided via
`ESEWA_MERCHANT_CODE=EPAYTEST`, `ESEWA_SECRET_KEY`, `ESEWA_SANDBOX=True`, and the sandbox payment
/ status URLs.

- `POST /api/payments/esewa/initiate/` — body `{ "order_id": "<uuid>" }`. Validates the order is
  an `esewa` payment, not paid, and has a positive total; generates a `transaction_uuid`, builds
  the HMAC-SHA256-signed form payload, and returns the fields plus the eSewa payment URL. The
  frontend auto-submits a hidden form to that URL.
  Response: `{ esewa_url, fields, ... }` where `fields` includes `amt`, `tAmt`, `pdc`, `txAmt`,
  `psc`, `scd`, `pid`, `su`, `fu`, `transaction_uuid`, `signed_field_names`, `signature`.
- `GET /api/payments/esewa/callback/` — eSewa redirects here with a base64-encoded `data` query
  param after payment. The backend decodes, verifies the signature, and on `COMPLETE` sets
  `is_paid=True`, `gateway_reference=transaction_code`, and transitions `status` to `confirmed`.
  Idempotent — safe on repeats.
- `POST /api/payments/esewa/status/` — body `{ "order_id": "<uuid>" }`. Queries eSewa's
  `/api/epay/transaction/status/` endpoint with the order's `transaction_uuid` and, on `COMPLETE`,
  confirms the order. Used as a fallback when the redirect callback is lost.

The eSewa integration lives in a self-contained `shop/payments/` module — config, errors, shared
signature/payload helpers (`build_esewa_payload`, `verify_esewa_signature`), and dedicated API
views — fully separated from `shop/views.py`.

### Cash on Delivery (COD)

`Order.payment_method` includes `cod`. COD orders require no online payment step at checkout and
are **not** gateway payments. The shop owner marks them paid / confirmed / fulfilled from the
admin (`/admin/`) using the existing "Mark selected orders as Paid/Confirmed/Fulfilled" actions.

### Payment fields on `Order`

- `gateway_reference` — eSewa `transaction_code` (or `ref_id` from status check) for gateway
  payments.
- `transaction_uuid` — unique transaction identifier generated at initiate, used for eSewa
  callback matching and status lookup.
- `is_paid` — auto set `True` on eSewa confirmation; manually via admin for COD/manual orders.
- `payment_status` — last known gateway status (`pending`, `COMPLETE`, `failed`, etc.).
- `is_gateway_payment` — `True` for `esewa`, `khalti`; `False` for COD and manual.

### Reserved gateways

Khalti remains a selectable value so the schema supports it later; wiring it would reuse the same
`gateway_reference` / `is_paid` contract with a small gateway module.

### Transactional Email

Order and payment notifications are sent through Django's configured mailer:

- **Order confirmation** to the customer, and **new-order** notification to the admin — fired
  automatically when the first line item is added to an order (`post_save` signal on `OrderItem`).
- **Payment success** to the customer, and **payment-received** notification to the admin — fired
  on gateway confirmation (`Order.mark_gateway_confirmed`) and when the admin marks an order paid.

The customer email comes from `Order.email` (new field, captured at checkout). Admin notifications
go to `DJANGO_ADMIN_EMAIL` and are skipped when it's unset. Emails are built in
`shop/services/email.py` from HTML + plain-text templates in `shop/templates/email/`.

Sending failures are logged, never raised — a broken mail backend cannot break ordering. Dev uses
the console backend (emails print to stdout); production sets `DJANGO_EMAIL_BACKEND` to an SMTP
backend plus `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_HOST_USER`,
`DJANGO_EMAIL_HOST_PASSWORD`, `DJANGO_EMAIL_USE_TLS` in `.env`.

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
Order: user(FK:User,null) customer_name(str,max=150) contact_info(str,max=150) email(email,blank) shipping_address_line(str,max=255) shipping_city(str,max=100) shipping_landmark(str,max=255,blank) total(decimal,max=10,dec=2) payment_method(choice:esewa,khalti,whatsapp,instagram) status(choice:pending,confirmed,fulfilled) created_at(auto)
OrderItem: order(FK:Order,related=items) variant(FK:ProductVariant) quantity(int) price(decimal,max=10,dec=2)
Review: product(FK:Product,related=reviews) reviewer_name(str,max=150) rating(int) review_text(text) created_at(auto)
BlogPost: slug(slug) title(str,max=200) excerpt(str,max=300) content(text) cover_image(image) published_at(datetime)
```
