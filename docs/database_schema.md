# InsightForge — Database Data Dictionary, Business Metrics & Data Quality Rules

This document details the PostgreSQL relational schema, table structures, column definitions, metric formulas, fan-out prevention rules, and data quality validation guidelines for **InsightForge**.

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

## 2. Centralized Canonical Business Metric Definitions

| Business Metric | Canonical Value | Formula / Calculation | Source Table(s) | Business Interpretation |
|---|---|---|---|---|
| **Product Revenue** | **R$ 13,221,498.11** | `SUM(order_items.price)` WHERE `orders.order_status = 'delivered'` | `order_items`, `orders` | Total net product sales value generated from fulfilled delivered orders. |
| **Freight Revenue** | **R$ 2,198,275.64** | `SUM(order_items.freight_value)` WHERE `orders.order_status = 'delivered'` | `order_items`, `orders` | Total shipping charges paid by customers on delivered orders. |
| **Gross Revenue** | **R$ 15,419,773.75** | `SUM(price + freight_value)` WHERE `orders.order_status = 'delivered'` | `order_items`, `orders` | Total top-line cash flow received including product prices and freight. |
| **Delivered Orders** | **96,478** | `COUNT(DISTINCT orders.order_id)` WHERE `order_status = 'delivered'` | `orders` | Count of successfully fulfilled e-commerce purchase orders. |
| **Active Customers** | **93,358** | `COUNT(DISTINCT customers.customer_unique_id)` WHERE `order_status = 'delivered'` | `customers`, `orders` | Count of unique individuals who placed at least one delivered order. |
| **Units Sold** | **110,197** | `COUNT(order_items.order_item_id)` WHERE `order_status = 'delivered'` | `order_items`, `orders` | Total number of individual items purchased across all delivered orders. |
| **Average Order Value (AOV)** | **R$ 159.83** | `Gross Revenue / COUNT(DISTINCT orders.order_id)` | `view_order_level_summary` | Average financial size per completed customer transaction (`15,419,773.75 / 96,478`). |
| **Customer Satisfaction (CSAT)** | **4.16 / 5.0** | `AVG(order_reviews.review_score)` | `order_reviews`, `orders` | Mean customer feedback score on a 1.0 to 5.0 scale (computed via separate CTE/subquery). |
| **Average Delivery Time** | **12.5 days** | `AVG(order_delivered_customer_date - order_purchase_timestamp)` in days | `orders` | Average elapsed calendar days from initial purchase to doorstep delivery. |

---

## 3. Data-Quality & Fan-Out Prevention Rules

1. **Fan-Out Join Multiplication Prevention (Strict Rule)**:
   - *Issue*: Orders can have multiple items AND multiple review records or payment splits (e.g., 547 orders in Olist have $>1$ review record). Joining `order_items` directly with `order_reviews` creates a cartesian product that duplicates line items and inflates revenue by R$ 69,891.80.
   - *Mandatory Rule*: Never join `order_reviews` or `order_payments` directly with `order_items` in line-item revenue sum queries. Calculate CSAT and review metrics via an independent CTE/subquery or use `view_order_level_summary`.
2. **Order Status Scoping**:
   - Financial KPIs (Revenue, AOV, Sales Volume) strictly filter for `order_status = 'delivered'`. Canceled, processing, or unavailable orders are excluded from financial revenue metrics to reflect actual realized cash flow.
3. **Uncategorized Products Handling**:
   - 610 products in Olist do not have a category translation. They are preserved in the catalog and modeled as `'Uncategorized'` using `COALESCE` without dropping rows.
4. **Chronological Validity**:
   - Timestamps must satisfy `order_delivered_customer_date >= order_purchase_timestamp`. Delivery durations $< 0$ or $> 365$ days are flagged in `data_quality.py`.

---

## 4. Analytical Views Summary

- `view_order_level_summary`: Order header grain rollup of items, product revenue, and freight value.
- `view_monthly_kpis_mom`: Monthly revenue, orders, AOV, and Month-over-Month (MoM) growth rates.
- `view_category_contribution`: Category unit sales, revenue, average price, CSAT, and revenue contribution %.
- `view_state_contribution`: State customer count, orders, gross revenue, freight cost, and state contribution %.
- `view_delivery_sla_performance`: Actual vs estimated delivery days and SLA status (`On-Time`, `Delayed`, `Undelivered`).
- `view_seller_performance`: Merchant volume, revenue, product diversity, and average review score.
