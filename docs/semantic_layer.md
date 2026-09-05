# InsightForge — Semantic Layer & Business Glossary Foundation

This document details the architectural foundation, machine-readable specifications, metric formulas, analytical dimensions, relationship graph, and Cartesian fan-out safety rules of the **InsightForge Semantic Layer** (Step 5).

---

> [!IMPORTANT]
> **Foundation Status Statement**: The current Step 5 implementation represents the **machine-readable semantic foundation** (YAML specifications, validator, and test suite). It provides controlled business logic and schema context for PostgreSQL tables. Features such as LangGraph AI agents, MCP tools, Text-to-SQL generation, RAG vector retrieval, and automated recommendations will be built on top of this foundation in subsequent project phases.

---

## 1. What is the Semantic Layer?

The **Semantic Layer** is an abstraction layer positioned between the raw PostgreSQL database schema and downstream consumers (BI dashboards, REST APIs, and future AI agents). It maps technical database objects (`insightforge.order_items`, `insightforge.orders`) into standard commercial concepts ("Product Revenue", "Delivered Orders", "AOV").

```
+-------------------------------------------------------------+
|                      React BI Dashboard                     |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                 FastAPI Analytics REST API                  |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|              INSIGHTFORGE SEMANTIC LAYER                    |
|  • Business Glossary       • Machine-Readable Metrics      |
|  • Analytical Dimensions   • Schema Graph & Join Semantics |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|              PostgreSQL (Olist Real Dataset)                |
+-------------------------------------------------------------+
```

---

## 2. Why InsightForge Needs It

1. **Eliminates Business Logic Ambiguity**: Defines explicit SQL aggregation rules for terms like "sales" vs "gross revenue" vs "product revenue".
2. **Guarantees Metric Integrity**: Prevents incorrect SQL queries (e.g., aggregating non-delivered orders or creating Cartesian product fan-outs).
3. **Machine-Readable AI Readiness**: Structures business definitions in standard YAML format, enabling upcoming Text-to-SQL generators and RAG agents to retrieve accurate schema context without guesswork.
4. **Centralized Data Governance**: Establishes a single source of truth shared across database views, Python analytics modules, REST API endpoints, and documentation.

---

## 3. Business Glossary

Controlled definitions for core commercial terms in InsightForge:

| Term Key | Display Name | Business Definition | Database Source | Canonical Benchmark |
|---|---|---|---|---|
| `revenue` | Revenue | Total monetary value collected on delivered orders (product + freight). | `order_items`, `orders` | R$ 15,419,773.75 |
| `product_revenue` | Product Revenue | Net merchandise sales value excluding shipping fees. | `order_items.price` | R$ 13,221,498.11 |
| `freight_revenue` | Freight Revenue | Shipping charges collected from customers. | `order_items.freight_value` | R$ 2,198,275.64 |
| `gross_revenue` | Gross Revenue | Combined top-line cash flow (Product + Freight). | `order_items` (price + freight) | R$ 15,419,773.75 |
| `delivered_orders` | Delivered Orders | Distinct count of purchase orders delivered to doorstep. | `orders.order_id` (`status='delivered'`) | 96,478 orders |
| `active_customers` | Active Customers | Unique customer individuals with at least one delivered order. | `customers.customer_unique_id` | 93,358 customers |
| `units_sold` | Units Sold | Total count of line items sold across delivered orders. | `order_items.order_item_id` | 110,197 units |
| `average_order_value` | Average Order Value (AOV) | Mean gross revenue generated per completed order transaction. | `gross_revenue / delivered_orders` | R$ 159.83 |
| `customer_satisfaction` | Customer Satisfaction (CSAT) | Mean rating score from post-purchase customer feedback (1–5 scale). | `order_reviews.review_score` | 4.16 / 5.0 |
| `on_time_delivery` | On-Time Delivery | SLA outcome where delivery date $\le$ estimated date. | `orders.order_delivered_customer_date` | SLA Met |
| `delayed_delivery` | Delayed Delivery | SLA outcome where delivery date $>$ estimated date. | `orders.order_delivered_customer_date` | SLA Missed |
| `undelivered_orders` | Undelivered Orders | Orders where customer delivery date IS NULL. | `orders.order_delivered_customer_date` | In-Transit / Canceled |
| `revenue_share` | Revenue Share | Percentage proportion contributed by a slice to company total. | `(slice_rev / total_rev) * 100` | Percentage |
| `order` | Order | Primary commercial purchase transaction entity. | `orders` table | Grain: 1 per order |
| `customer` | Customer | Purchasing consumer dimension and location entity. | `customers` table | Grain: 1 per session |
| `product` | Product | Merchandise catalog item entity with category translations. | `products` table | Grain: 1 per item |
| `seller` | Seller | Merchant seller partner fulfilling order line items. | `sellers` table | Grain: 1 per merchant |
| `payment_method` | Payment Method | Tender instrument used (credit card, boleto, voucher, debit). | `order_payments` table | Split transactions allowed |
| `review_score` | Review Score | Quantitative 1–5 rating provided in review survey. | `order_reviews` table | 1 to 5 stars |

---

## 4. Metric Definitions

Machine-readable metrics defined in `semantic/metrics.yaml`:

```yaml
gross_revenue:
  metric_name: Gross Revenue
  formula: SUM(order_items.price + order_items.freight_value)
  source_tables: [order_items, orders]
  filters: ["orders.order_status = 'delivered'"]
  unit: BRL (R$)
  canonical_value: 15419773.75

aov:
  metric_name: Average Order Value
  formula: gross_revenue / delivered_orders
  source_tables: [view_order_level_summary, order_items, orders]
  unit: BRL per order (R$/order)
  canonical_value: 159.83

csat:
  metric_name: Customer Satisfaction Score
  formula: AVG(order_reviews.review_score)
  source_tables: [order_reviews, orders]
  unit: rating scale (1.0 - 5.0)
  canonical_value: 4.16
```

---

## 5. Analytical Dimensions

Dimensions defined in `semantic/dimensions.yaml`:

1. `date`: Order purchase timestamp (`orders.order_purchase_timestamp`).
2. `month`: Billing month (`DATE_TRUNC('month', order_purchase_timestamp)`).
3. `product_category`: English product category (`products.product_category_name_english`).
4. `customer_state`: Brazilian 2-letter state code (`customers.customer_state`).
5. `seller`: Merchant identifier key (`sellers.seller_id`).
6. `payment_type`: Tender method (`order_payments.payment_type`: `credit_card`, `boleto`, `voucher`, `debit_card`).
7. `order_status`: Lifecycle state (`orders.order_status`: `delivered`, `shipped`, `canceled`, etc.).
8. `review_score`: Feedback star rating (`order_reviews.review_score`: 1 to 5).
9. `delivery_status`: SLA outcome (`view_delivery_sla_performance.delivery_status`: `On-Time`, `Delayed`, `Undelivered`).

---

## 6. Table Relationships & Join Graph

Schema relationships documented in `semantic/relationships.yaml`:

- `customers` $(1) \longrightarrow (N)$ `orders` [Key: `customer_id`]
- `orders` $(1) \longrightarrow (N)$ `order_items` [Key: `order_id`]
- `products` $(1) \longrightarrow (N)$ `order_items` [Key: `product_id`]
- `sellers` $(1) \longrightarrow (N)$ `order_items` [Key: `seller_id`]
- `orders` $(1) \longrightarrow (N)$ `order_payments` [Key: `order_id`]
- `orders` $(1) \longrightarrow (N)$ `order_reviews` [Key: `order_id`]

---

## 7. Business Language Synonyms Dictionary

To assist AI agents and text processing, business natural language phrases map to canonical metric targets:

| User Business Term | Semantic Target | Formula / Condition |
|---|---|---|
| "sales", "total sales" | `gross_revenue` | `SUM(price + freight_value) WHERE status='delivered'` |
| "merchandise sales", "item sales" | `product_revenue` | `SUM(price) WHERE status='delivered'` |
| "shipping fees", "freight" | `freight_revenue` | `SUM(freight_value) WHERE status='delivered'` |
| "completed orders", "order count" | `delivered_orders` | `COUNT(DISTINCT order_id) WHERE status='delivered'` |
| "customers", "buyers" | `active_customers` | `COUNT(DISTINCT customer_unique_id) WHERE status='delivered'` |
| "average basket size", "AOV" | `aov` | `gross_revenue / delivered_orders` |
| "customer rating", "satisfaction" | `csat` | `AVG(review_score) WHERE status='delivered'` |
| "late deliveries", "missed SLA" | `delayed_delivery` | `order_delivered_customer_date > order_estimated_delivery_date` |

---

## 8. Fan-Out Multiplication Protection Rules

> [!WARNING]
> **Cartesian Fan-Out Risk**: Naive SQL joins between `order_items` and `order_reviews` or `order_payments` create cross-product row multiplication. For example, joining 547 multi-review orders directly to `order_items` duplicates line items, inflating revenue by R$ 69,891.80.

**Mandatory Protection Guidelines**:
1. **Never join `order_reviews` or `order_payments` directly with `order_items` in line-item revenue sum queries**.
2. Calculate CSAT and customer review scores in an independent CTE or subquery before joining to revenue totals.
3. Utilize the pre-aggregated view `view_order_level_summary` for order-level metric rollups.

---

## 9. Future AI Roadmap Integration

In future steps, this semantic foundation will power AI agent capabilities:
- **Text-to-SQL Generation**: The YAML specs will be injected into prompt contexts to guide LLMs in generating syntactically valid, fan-out-safe SQL queries.
- **RAG Retrieval Pipeline**: Vector embeddings of `business_glossary.yaml` and `metrics.yaml` will enable intent classification and dictionary lookup for natural language questions.
- **Root-Cause Analysis Agents**: LangGraph agents will utilize dimension trees and metric definitions to isolate revenue drop drivers automatically.
