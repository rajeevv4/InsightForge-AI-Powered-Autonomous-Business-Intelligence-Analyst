# InsightForge — Backend REST API Documentation

This document provides the complete API reference for the **InsightForge FastAPI Backend Service**.

- **Base URL**: `http://localhost:8000/api`
- **Interactive OpenAPI/Swagger UI**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`

---

## 📌 Endpoints Summary

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | System health check and PostgreSQL database connectivity status |
| `GET` | `/api/kpis` | Canonical executive summary KPIs (Product Rev, Freight, Gross Rev, Orders, AOV, CSAT) |
| `GET` | `/api/analytics/revenue-trend` | Monthly sales trend, order volume, AOV, and MoM growth rates |
| `GET` | `/api/analytics/categories` | Product category performance, unit sales, CSAT, and revenue share % |
| `GET` | `/api/analytics/states` | Regional state performance, active customer count, and state revenue share % |
| `GET` | `/api/analytics/sellers` | Top merchant performance (order volume, sales revenue, product count, CSAT) |
| `GET` | `/api/analytics/payments` | Payment method breakdown (credit card, boleto, voucher, debit card) and installments |
| `GET` | `/api/analytics/delivery` | Fulfillment SLA status breakdown (`On-Time`, `Delayed`, `Undelivered`) and delay days |
| `GET` | `/api/data-quality` | Automated 10-check data quality audit findings and join safety status |

---

## 📖 Endpoint Details & Sample JSON Responses

### 1. `GET /api/health`
**Description**: Verifies API operational status and PostgreSQL database connection.

**Sample Response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "service": "InsightForge",
  "version": "0.1.0"
}
```

---

### 2. `GET /api/kpis`
**Description**: Returns canonical top-line financial metrics for delivered orders.

**Sample Response**:
```json
{
  "product_revenue": 13221498.11,
  "freight_revenue": 2198275.64,
  "gross_revenue": 15419773.75,
  "delivered_orders": 96478,
  "active_customers": 93358,
  "units_sold": 110197,
  "aov": 159.83,
  "csat": 4.16
}
```

---

### 3. `GET /api/analytics/revenue-trend`
**Description**: Returns monthly sales trends and Month-over-Month (MoM) growth rates.

**Sample Response**:
```json
[
  {
    "month": "2018-08-01",
    "total_orders": 6358,
    "total_items_sold": 7183,
    "product_revenue": 854686.32,
    "freight_revenue": 149454.21,
    "gross_revenue": 1004140.53,
    "aov": 157.93,
    "prev_month_revenue": 1027839.26,
    "mom_revenue_growth_pct": -2.31,
    "mom_order_growth_pct": -2.62,
    "mom_aov_growth_pct": 0.32
  }
]
```

---

### 4. `GET /api/analytics/categories?limit=5`
**Description**: Returns top product categories sorted by revenue contribution %.

**Parameters**:
- `limit` *(int, optional, default=10, max=100)*: Number of categories to return.

**Sample Response**:
```json
[
  {
    "category": "health_beauty",
    "total_orders": 8836,
    "units_sold": 9670,
    "total_revenue": 1237439.95,
    "avg_item_price": 127.97,
    "avg_review_score": 4.19,
    "revenue_share_percent": 9.36
  }
]
```

---

### 5. `GET /api/analytics/states`
**Description**: Returns sales and customer distribution across Brazilian states.

**Sample Response**:
```json
[
  {
    "state": "SP",
    "active_customers": 39156,
    "total_orders": 40494,
    "total_product_revenue": 5074213.90,
    "total_freight_revenue": 695489.25,
    "total_gross_revenue": 5769703.15,
    "avg_freight_cost": 15.15,
    "revenue_share_percent": 38.33
  }
]
```

---

### 6. `GET /api/analytics/sellers?limit=5`
**Description**: Returns top merchants sorted by total sales revenue.

**Parameters**:
- `limit` *(int, optional, default=10, max=100)*: Number of sellers to return.

---

### 7. `GET /api/analytics/delivery`
**Description**: Returns delivery SLA status breakdown (`On-Time`, `Delayed`, `Undelivered`).

**Sample Response**:
```json
[
  {
    "delivery_status": "On-Time",
    "order_count": 88644,
    "percentage": 91.88,
    "avg_actual_delivery_days": 10.88,
    "avg_estimated_delivery_days": 24.31,
    "avg_delay_days": 0.0
  },
  {
    "delivery_status": "Delayed",
    "order_count": 7826,
    "percentage": 8.11,
    "avg_actual_delivery_days": 31.52,
    "avg_estimated_delivery_days": 21.05,
    "avg_delay_days": 10.47
  }
]
```

---

### 8. `GET /api/data-quality`
**Description**: Returns the automated 10-point data quality audit summary.

**Sample Response**:
```json
{
  "audit_status": "PASS",
  "table_row_counts": {
    "customers": 99441,
    "products": 32951,
    "sellers": 3095,
    "orders": 99441,
    "order_items": 112650,
    "order_payments": 103886,
    "order_reviews": 99224
  },
  "primary_key_uniqueness": "PASS (0 duplicates)",
  "foreign_key_integrity": "PASS (0 orphans)",
  "domain_bounds_status": "PASS (0 out of range values)",
  "join_safety_status": "PASS (0.00 discrepancy)",
  "anomalies_flagged": []
}
```
