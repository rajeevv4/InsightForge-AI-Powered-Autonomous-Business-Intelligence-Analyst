-- ============================================================================
-- InsightForge - Analytical Views (PostgreSQL)
-- Standardized BI Aggregations & Analytical Summary Views
-- ============================================================================

SET search_path TO insightforge, public;

-- 1. Monthly Revenue & Order Volume Summary
CREATE OR REPLACE VIEW view_monthly_sales_performance AS
SELECT 
    DATE_TRUNC('month', o.order_purchase_timestamp)::DATE AS sales_month,
    COUNT(DISTINCT o.order_id) AS total_orders,
    COUNT(oi.order_item_id) AS total_items_sold,
    SUM(oi.price) AS total_product_revenue,
    SUM(oi.freight_value) AS total_freight_revenue,
    SUM(oi.price + oi.freight_value) AS total_gross_revenue,
    ROUND(AVG(oi.price), 2) AS average_order_item_price
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered'
GROUP BY 1
ORDER BY 1 DESC;

-- 2. Category Performance Summary (English Categories)
CREATE OR REPLACE VIEW view_category_performance AS
SELECT 
    COALESCE(p.product_category_name_english, 'Uncategorized') AS category_name,
    COUNT(DISTINCT oi.order_id) AS total_orders,
    COUNT(oi.order_item_id) AS total_units_sold,
    SUM(oi.price) AS total_revenue,
    ROUND(AVG(oi.price), 2) AS avg_item_price,
    ROUND(AVG(r.review_score), 2) AS avg_review_score
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
JOIN orders o ON oi.order_id = o.order_id
LEFT JOIN order_reviews r ON oi.order_id = r.order_id
WHERE o.order_status = 'delivered'
GROUP BY COALESCE(p.product_category_name_english, 'Uncategorized')
ORDER BY total_revenue DESC;

-- 3. Regional Customer Sales Summary
CREATE OR REPLACE VIEW view_state_sales_performance AS
SELECT 
    c.customer_state,
    COUNT(DISTINCT c.customer_unique_id) AS unique_customers,
    COUNT(DISTINCT o.order_id) AS total_orders,
    SUM(oi.price) AS total_revenue,
    ROUND(AVG(oi.freight_value), 2) AS avg_freight_cost
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered'
GROUP BY c.customer_state
ORDER BY total_revenue DESC;

-- 4. Delivery Fulfillment SLA Performance
CREATE OR REPLACE VIEW view_delivery_sla_performance AS
SELECT 
    order_id,
    order_purchase_timestamp,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    EXTRACT(DAY FROM (order_delivered_customer_date - order_purchase_timestamp)) AS actual_delivery_days,
    EXTRACT(DAY FROM (order_estimated_delivery_date - order_purchase_timestamp)) AS estimated_delivery_days,
    CASE 
        WHEN order_delivered_customer_date <= order_estimated_delivery_date THEN 'On-Time'
        WHEN order_delivered_customer_date IS NULL THEN 'Undelivered'
        ELSE 'Delayed'
    END AS delivery_status
FROM orders
WHERE order_status = 'delivered';
