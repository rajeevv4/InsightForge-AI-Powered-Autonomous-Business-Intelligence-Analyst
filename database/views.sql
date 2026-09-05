-- ============================================================================
-- InsightForge - Analytical Views (PostgreSQL)
-- Standardized BI Aggregations, Window Functions & Analytical Views
-- ============================================================================

SET search_path TO insightforge, public;

-- Drop existing views in reverse dependency order
DROP VIEW IF EXISTS view_seller_performance CASCADE;
DROP VIEW IF EXISTS view_delivery_sla_performance CASCADE;
DROP VIEW IF EXISTS view_state_contribution CASCADE;
DROP VIEW IF EXISTS view_state_sales_performance CASCADE;
DROP VIEW IF EXISTS view_category_contribution CASCADE;
DROP VIEW IF EXISTS view_category_performance CASCADE;
DROP VIEW IF EXISTS view_monthly_kpis_mom CASCADE;
DROP VIEW IF EXISTS view_monthly_sales_performance CASCADE;
DROP VIEW IF EXISTS view_order_level_summary CASCADE;

-- ----------------------------------------------------------------------------
-- 1. Order-Level Summary View (Prevents Cartesian Fan-Out Join Multiplication)
-- ----------------------------------------------------------------------------
CREATE VIEW view_order_level_summary AS
SELECT 
    o.order_id,
    o.customer_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,
    COUNT(oi.order_item_id) AS item_count,
    COALESCE(SUM(oi.price), 0) AS total_product_amount,
    COALESCE(SUM(oi.freight_value), 0) AS total_freight_amount,
    COALESCE(SUM(oi.price + oi.freight_value), 0) AS gross_order_amount
FROM orders o
LEFT JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id, o.customer_id, o.order_status, o.order_purchase_timestamp, 
         o.order_approved_at, o.order_delivered_carrier_date, 
         o.order_delivered_customer_date, o.order_estimated_delivery_date;

-- ----------------------------------------------------------------------------
-- 2. Monthly Revenue, Order Volume, AOV & Month-over-Month (MoM) Growth
-- ----------------------------------------------------------------------------
CREATE VIEW view_monthly_kpis_mom AS
WITH monthly_base AS (
    SELECT 
        DATE_TRUNC('month', order_purchase_timestamp)::DATE AS sales_month,
        COUNT(DISTINCT order_id) AS total_orders,
        SUM(total_product_amount) AS product_revenue,
        SUM(total_freight_amount) AS freight_revenue,
        SUM(gross_order_amount) AS gross_revenue,
        SUM(item_count) AS total_items_sold,
        ROUND(SUM(gross_order_amount) / NULLIF(COUNT(DISTINCT order_id), 0), 2) AS aov
    FROM view_order_level_summary
    WHERE order_status = 'delivered'
    GROUP BY 1
)
SELECT 
    sales_month,
    total_orders,
    total_items_sold,
    product_revenue,
    freight_revenue,
    gross_revenue,
    aov,
    LAG(gross_revenue) OVER (ORDER BY sales_month) AS prev_month_revenue,
    ROUND(
        (gross_revenue - LAG(gross_revenue) OVER (ORDER BY sales_month)) / 
        NULLIF(LAG(gross_revenue) OVER (ORDER BY sales_month), 0) * 100, 2
    ) AS mom_revenue_growth_pct,
    LAG(total_orders) OVER (ORDER BY sales_month) AS prev_month_orders,
    ROUND(
        (total_orders - LAG(total_orders) OVER (ORDER BY sales_month))::NUMERIC / 
        NULLIF(LAG(total_orders) OVER (ORDER BY sales_month), 0) * 100, 2
    ) AS mom_order_growth_pct,
    LAG(aov) OVER (ORDER BY sales_month) AS prev_month_aov,
    ROUND(
        (aov - LAG(aov) OVER (ORDER BY sales_month)) / 
        NULLIF(LAG(aov) OVER (ORDER BY sales_month), 0) * 100, 2
    ) AS mom_aov_growth_pct
FROM monthly_base
ORDER BY sales_month DESC;

-- Backward compatibility alias view
CREATE VIEW view_monthly_sales_performance AS
SELECT 
    sales_month,
    total_orders,
    total_items_sold,
    product_revenue AS total_product_revenue,
    freight_revenue AS total_freight_revenue,
    gross_revenue AS total_gross_revenue,
    aov AS average_order_item_price
FROM view_monthly_kpis_mom;

-- ----------------------------------------------------------------------------
-- 3. Category Revenue Performance & Overall Revenue Contribution %
-- ----------------------------------------------------------------------------
CREATE VIEW view_category_contribution AS
WITH totals AS (
    SELECT SUM(price) AS overall_company_revenue
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
)
SELECT 
    COALESCE(p.product_category_name_english, 'Uncategorized') AS category_name,
    COUNT(DISTINCT oi.order_id) AS total_orders,
    COUNT(oi.order_item_id) AS units_sold,
    SUM(oi.price) AS total_revenue,
    ROUND(AVG(oi.price), 2) AS avg_item_price,
    ROUND(AVG(r.review_score), 2) AS avg_review_score,
    ROUND((SUM(oi.price) / t.overall_company_revenue) * 100, 2) AS revenue_contribution_pct
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
JOIN orders o ON oi.order_id = o.order_id
LEFT JOIN order_reviews r ON oi.order_id = r.order_id
CROSS JOIN totals t
WHERE o.order_status = 'delivered'
GROUP BY COALESCE(p.product_category_name_english, 'Uncategorized'), t.overall_company_revenue
ORDER BY total_revenue DESC;

-- Backward compatibility alias view
CREATE VIEW view_category_performance AS
SELECT 
    category_name,
    total_orders,
    units_sold AS total_units_sold,
    total_revenue,
    avg_item_price,
    avg_review_score
FROM view_category_contribution;

-- ----------------------------------------------------------------------------
-- 4. Regional Customer State Revenue & State Contribution %
-- ----------------------------------------------------------------------------
CREATE VIEW view_state_contribution AS
WITH totals AS (
    SELECT SUM(price) AS overall_company_revenue
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
)
SELECT 
    c.customer_state,
    COUNT(DISTINCT c.customer_unique_id) AS active_customers,
    COUNT(DISTINCT o.order_id) AS total_orders,
    SUM(oi.price) AS total_product_revenue,
    SUM(oi.freight_value) AS total_freight_revenue,
    SUM(oi.price + oi.freight_value) AS total_gross_revenue,
    ROUND(AVG(oi.freight_value), 2) AS avg_freight_cost,
    ROUND((SUM(oi.price) / t.overall_company_revenue) * 100, 2) AS state_revenue_contribution_pct
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
CROSS JOIN totals t
WHERE o.order_status = 'delivered'
GROUP BY c.customer_state, t.overall_company_revenue
ORDER BY total_gross_revenue DESC;

-- Backward compatibility alias view
CREATE VIEW view_state_sales_performance AS
SELECT 
    customer_state,
    active_customers AS unique_customers,
    total_orders,
    total_product_revenue AS total_revenue,
    avg_freight_cost
FROM view_state_contribution;

-- ----------------------------------------------------------------------------
-- 5. Delivery SLA & Fulfillment Performance Analysis
-- ----------------------------------------------------------------------------
CREATE VIEW view_delivery_sla_performance AS
SELECT 
    order_id,
    customer_id,
    order_purchase_timestamp,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    CASE 
        WHEN order_delivered_customer_date IS NOT NULL AND order_delivered_customer_date >= order_purchase_timestamp THEN
            ROUND(EXTRACT(EPOCH FROM (order_delivered_customer_date - order_purchase_timestamp)) / 86400.0, 2)
        ELSE NULL
    END AS actual_delivery_days,
    ROUND(EXTRACT(EPOCH FROM (order_estimated_delivery_date - order_purchase_timestamp)) / 86400.0, 2) AS estimated_delivery_days,
    CASE 
        WHEN order_delivered_customer_date IS NULL THEN 'Undelivered'
        WHEN order_delivered_customer_date <= order_estimated_delivery_date THEN 'On-Time'
        ELSE 'Delayed'
    END AS delivery_status,
    CASE 
        WHEN order_delivered_customer_date > order_estimated_delivery_date THEN
            ROUND(EXTRACT(EPOCH FROM (order_delivered_customer_date - order_estimated_delivery_date)) / 86400.0, 2)
        ELSE 0
    END AS delay_days
FROM orders
WHERE order_status = 'delivered';

-- ----------------------------------------------------------------------------
-- 6. Merchant / Seller Performance Summary
-- ----------------------------------------------------------------------------
CREATE VIEW view_seller_performance AS
SELECT 
    s.seller_id,
    s.seller_city,
    s.seller_state,
    COUNT(DISTINCT oi.order_id) AS total_orders_fulfilled,
    COUNT(oi.order_item_id) AS units_sold,
    COUNT(DISTINCT oi.product_id) AS unique_products_offered,
    SUM(oi.price) AS total_sales_revenue,
    ROUND(AVG(r.review_score), 2) AS avg_seller_review_score
FROM sellers s
JOIN order_items oi ON s.seller_id = oi.seller_id
JOIN orders o ON oi.order_id = o.order_id
LEFT JOIN order_reviews r ON oi.order_id = r.order_id
WHERE o.order_status = 'delivered'
GROUP BY s.seller_id, s.seller_city, s.seller_state
ORDER BY total_sales_revenue DESC;
