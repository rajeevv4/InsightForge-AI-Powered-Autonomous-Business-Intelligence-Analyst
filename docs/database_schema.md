# InsightForge — Database Data Dictionary & Metric Definitions

This document details the PostgreSQL relational schema, table structures, column definitions, table grains, primary/foreign keys, and key business metrics for **InsightForge**.

---

## 1. Relational Schema Summary

**PostgreSQL Schema**: `insightforge`

| Table Name | Grain | Primary Key | Foreign Keys | Description |
|---|---|---|---|---|
| `customers` | 1 row per order customer session | `customer_id` | - | Customer order location and unique tracking hash across Brazil. |
| `products` | 1 row per product item | `product_id` | - | Product catalog details with English translations and physical dimensions. |
| `sellers` | 1 row per seller | `seller_id` | - | Seller/merchant directory and location details. |
| `orders` | 1 row per purchase order | `order_id` | `customer_id` -> `customers` | Order header fact table recording timestamps across fulfillment stages. |
| `order_items` | 1 row per item in an order | (`order_id`, `order_item_id`) | `order_id` -> `orders`<br>`product_id` -> `products`<br>`seller_id` -> `sellers` | Line-item pricing, freight cost, seller assignment. |
| `order_payments` | 1 row per payment transaction split | (`order_id`, `payment_sequential`) | `order_id` -> `orders` | Payment methods (credit card, boleto, voucher, debit), installments, values. |
| `order_reviews` | 1 row per review response per order | (`review_id`, `order_id`) | `order_id` -> `orders` | Customer rating score (1–5) and optional text comments. |

---

## 2. Table Column Specifications

### `customers`
- `customer_id` (VARCHAR(32), PK): Order-specific customer key.
- `customer_unique_id` (VARCHAR(32), NOT NULL): Unique customer hash across repeated orders.
- `customer_zip_code_prefix` (VARCHAR(10)): Zip code prefix.
- `customer_city` (VARCHAR(100)): City name.
- `customer_state` (VARCHAR(5)): 2-letter state code (e.g. SP, RJ, MG).

### `products`
- `product_id` (VARCHAR(32), PK): Product unique identifier.
- `product_category_name` (VARCHAR(100)): Original category name in Portuguese.
- `product_category_name_english` (VARCHAR(100)): Translated category name in English.
- `product_name_length` (INT): Length of product title.
- `product_description_length` (INT): Length of product description text.
- `product_photos_qty` (INT): Number of published product photos.
- `product_weight_g` (INT): Physical weight in grams.
- `product_length_cm`, `product_height_cm`, `product_width_cm` (INT): Physical dimensions.

### `sellers`
- `seller_id` (VARCHAR(32), PK): Merchant identifier.
- `seller_zip_code_prefix` (VARCHAR(10)): Zip code prefix.
- `seller_city` (VARCHAR(100)): City name.
- `seller_state` (VARCHAR(5)): State code.

### `orders`
- `order_id` (VARCHAR(32), PK): Unique order identifier.
- `customer_id` (VARCHAR(32), FK): Links to `customers`.
- `order_status` (VARCHAR(20)): Order state (`delivered`, `shipped`, `canceled`, `invoiced`, `processing`).
- `order_purchase_timestamp` (TIMESTAMP): Purchase datetime.
- `order_approved_at` (TIMESTAMP): Payment approval datetime.
- `order_delivered_carrier_date` (TIMESTAMP): Hand-off datetime to logistics carrier.
- `order_delivered_customer_date` (TIMESTAMP): Actual delivery datetime to customer.
- `order_estimated_delivery_date` (TIMESTAMP): Expected delivery datetime.

### `order_items`
- `order_id` (VARCHAR(32), FK): Links to `orders`.
- `order_item_id` (INT): Sequential item number within order.
- `product_id` (VARCHAR(32), FK): Links to `products`.
- `seller_id` (VARCHAR(32), FK): Links to `sellers`.
- `shipping_limit_date` (TIMESTAMP): Seller dispatch deadline.
- `price` (NUMERIC(10, 2)): Item price in BRL (R$).
- `freight_value` (NUMERIC(10, 2)): Shipping charge per item in BRL (R$).

### `order_payments`
- `order_id` (VARCHAR(32), FK): Links to `orders`.
- `payment_sequential` (INT): Payment split index.
- `payment_type` (VARCHAR(30)): `credit_card`, `boleto`, `voucher`, `debit_card`.
- `payment_installments` (INT): Number of monthly installments.
- `payment_value` (NUMERIC(10, 2)): Amount paid in BRL (R$).

### `order_reviews`
- `review_id` (VARCHAR(32)): Review transaction key.
- `order_id` (VARCHAR(32), FK): Links to `orders`.
- `review_score` (INT): Satisfaction score (1 to 5).
- `review_comment_title` (TEXT): Feedback title text.
- `review_comment_message` (TEXT): Feedback body text.
- `review_creation_date` (TIMESTAMP): Survey creation datetime.
- `review_answer_timestamp` (TIMESTAMP): Survey response submission datetime.

---

## 3. Core Business Metric Formulas

1. **Product Revenue**: `SUM(order_items.price)` where `order_status = 'delivered'`.
2. **Freight Revenue**: `SUM(order_items.freight_value)` where `order_status = 'delivered'`.
3. **Gross Revenue**: `SUM(order_items.price + order_items.freight_value)` where `order_status = 'delivered'`.
4. **Average Order Value (AOV)**: `Gross Revenue / COUNT(DISTINCT orders.order_id)`.
5. **Customer Satisfaction Score (CSAT)**: `AVG(order_reviews.review_score)`.
6. **On-Time Delivery Rate (%)**: `(COUNT(orders delivered before or on estimated date) / TOTAL delivered orders) * 100`.
