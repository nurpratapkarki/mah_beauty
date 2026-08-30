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

| Endpoint | Notes |
|---|---|
| `/api/categories/` | standard CRUD |
| `/api/products/` | filter by `category`, `is_featured`, `is_best_seller`; search by name/description; extra actions: `featured/`, `best_sellers/` |
| `/api/variants/` | filter by `product`; search by sku/qr/shade; extra action: `in_stock/` |
| `/api/wishlists/` | extra action: `mine/` (GET current user's wishlist, POST to add a variant) |
| `/api/carts/` | extra actions: `mine/` (resolve current user or guest cart), `add_item/`, `remove_item/` |
| `/api/orders/` | guest checkout allowed; extra actions: `cancel/`, `my_orders/` (authenticated) |
| `/api/payments/fonepay/qr/` | `POST` — generate a FonePay dynamic QR for an order (see Payment Integration) |
| `/api/payments/fonepay/status/` | `POST` — check FonePay status and confirm an order |
| `/api/reviews/` | filter by `product` |
| `/api/blog/` | lookup by `slug` instead of id |

## Payment Integration

The backend supports **FonePay dynamic QR** (live gateway) and **Cash on Delivery (COD)**, plus
the legacy manual channels (WhatsApp / Instagram). eSewa / Khalti remain reserved (not wired).

### FonePay Dynamic QR

`Order.payment_method` includes `fonepay`. Config is read from `.env` (see `mah_beauty_project/
settings.py`); nothing secret lives in versioned code.

- `POST /api/payments/fonepay/qr/` — body `{ "order_id": "<uuid>" }`. Validates the order is a
  `fonepay` payment, not paid, and has a positive total; records the PRN and returns a QR to
  render.
  Response: `{ order_id, prn, amount, qr, qr_message, realtime, payment_status }`.
- `POST /api/payments/fonepay/status/` — body `{ "prn": "<prn>" }`. Queries FonePay and, on
  `COMPLETED`, sets `is_paid=True`, `gateway_reference=fonepayTraceId`, transitions `status` to
  `confirmed`. Idempotent — safe to re-check.
- `POST /api/payments/fonepay/refund/` — body `{ "order_id": "<uuid>", "invoice_number": "...",
  "invoice_date": "YYYY-MM-DD", "transaction_amount"? }`. Posts a FonePay tax refund for a paid
  FonePay order (uses `order.gateway_reference` as the trace ID and `order.prn` as the merchant
  PRN; amount defaults to the order total).

**Tax refund QR generation**: `FonepayClient.generate_qr()` accepts optional `tax_amount` /
`tax_refund`, which extend the HMAC message (`AMOUNT,PRN,MERCHANT-CODE,REMARKS1,REMARKS2,
TAXAMOUNT,TAXREFUND`) and add `taxAmount`/`taxRefund` to the request payload. When omitted,
the fields are not sent.

**Real-time auto-verification**: when FonePay returns a `thirdpartyQrWebSocketUrl` on QR
generation, the backend opens that socket in a background thread and listens for
`transactionStatus` messages. On `paymentSuccess` it cross-checks against
`thirdPartyDynamicQrGetStatus` and confirms the order automatically — no frontend polling
needed. The status endpoint remains as a fallback. Real-time monitoring requires the
`websockets` package (a runtime dependency).

The FonePay integration lives in a self-contained `shop/payments/` module — client, config,
errors, shared domain helpers (`get_client`, `confirm_paid_order`, `is_fonepay_payment`, etc.),
realtime monitor, and dedicated API views — fully separated from `shop/views.py`.

### Cash on Delivery (COD)

`Order.payment_method` includes `cod`. COD orders require no online payment step at checkout and
are **not** gateway payments. The shop owner marks them paid / confirmed / fulfilled from the
admin (`/admin/`) using the existing "Mark selected orders as Paid/Confirmed/Fulfilled" actions.

### Payment fields on `Order`

- `gateway_reference` — FonePay trace ID for gateway payments.
- `is_paid` — auto set `True` on FonePay confirmation; manually via admin for COD/manual orders.
- `prn` / `payment_status` — FonePay payment reference number and last known status.
- `is_gateway_payment` — `True` for `fonepay`, `esewa`, `khalti`; `False` for COD and manual.

### Reserved gateways

eSewa and Khalti remain selectable values so the schema supports them later; wiring them would
reuse the same `gateway_reference` / `is_paid` contract with a small gateway module.

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
