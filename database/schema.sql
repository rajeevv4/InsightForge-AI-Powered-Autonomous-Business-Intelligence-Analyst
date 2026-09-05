-- ============================================================================
-- InsightForge - Database Schema DDL (PostgreSQL)
-- Domain: E-Commerce Business Intelligence Analytics (Olist Data Model)
-- Phase 1: Core Relational Tables, Constraints, and Performance Indexes
-- ============================================================================

-- 1. Create Schema
CREATE SCHEMA IF NOT EXISTS insightforge;
SET search_path TO insightforge, public;

-- Drop existing tables in reverse dependency order if resetting
DROP TABLE IF EXISTS order_reviews CASCADE;
DROP TABLE IF EXISTS order_payments CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS sellers CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

-- ----------------------------------------------------------------------------
-- Table 1: CUSTOMERS (Customer Dimension & Location)
-- ----------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id VARCHAR(32) PRIMARY KEY,
    customer_unique_id VARCHAR(32) NOT NULL,
    customer_zip_code_prefix VARCHAR(10),
    customer_city VARCHAR(100),
    customer_state VARCHAR(5)
);

COMMENT ON TABLE customers IS 'Customer dimension table tracking individual orders and unique customer identifiers across Brazil';
COMMENT ON COLUMN customers.customer_id IS 'Primary key corresponding to a specific customer order session';
COMMENT ON COLUMN customers.customer_unique_id IS 'Unique identifier for a customer across multiple orders';

-- ----------------------------------------------------------------------------
-- Table 2: PRODUCTS (Product Catalog Dimension with English Translation)
-- ----------------------------------------------------------------------------
CREATE TABLE products (
    product_id VARCHAR(32) PRIMARY KEY,
    product_category_name VARCHAR(100),
    product_category_name_english VARCHAR(100),
    product_name_length INT,
    product_description_length INT,
    product_photos_qty INT,
    product_weight_g INT,
    product_length_cm INT,
    product_height_cm INT,
    product_width_cm INT
);

COMMENT ON TABLE products IS 'Product dimension table containing category translations and physical specifications';

-- ----------------------------------------------------------------------------
-- Table 3: SELLERS (Merchant / Seller Dimension)
-- ----------------------------------------------------------------------------
CREATE TABLE sellers (
    seller_id VARCHAR(32) PRIMARY KEY,
    seller_zip_code_prefix VARCHAR(10),
    seller_city VARCHAR(100),
    seller_state VARCHAR(5)
);

COMMENT ON TABLE sellers IS 'Seller/Merchant dimension table detailing merchant location';

-- ----------------------------------------------------------------------------
-- Table 4: ORDERS (Order Lifecycle Header Fact Table)
-- ----------------------------------------------------------------------------
CREATE TABLE orders (
    order_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    order_status VARCHAR(20) NOT NULL,
    order_purchase_timestamp TIMESTAMP NOT NULL,
    order_approved_at TIMESTAMP,
    order_delivered_carrier_date TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP
);

COMMENT ON TABLE orders IS 'Primary order fact table recording timestamps across the purchase fulfillment lifecycle';

-- ----------------------------------------------------------------------------
-- Table 5: ORDER_ITEMS (Line-Item Fact Table)
-- ----------------------------------------------------------------------------
CREATE TABLE order_items (
    order_id VARCHAR(32) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    order_item_id INT NOT NULL,
    product_id VARCHAR(32) NOT NULL REFERENCES products(product_id),
    seller_id VARCHAR(32) NOT NULL REFERENCES sellers(seller_id),
    shipping_limit_date TIMESTAMP,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    freight_value NUMERIC(10, 2) NOT NULL CHECK (freight_value >= 0),
    PRIMARY KEY (order_id, order_item_id)
);

COMMENT ON TABLE order_items IS 'Line-item transaction table connecting orders, products, and sellers with item price and freight';

-- ----------------------------------------------------------------------------
-- Table 6: ORDER_PAYMENTS (Payment Transaction Details)
-- ----------------------------------------------------------------------------
CREATE TABLE order_payments (
    order_id VARCHAR(32) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    payment_sequential INT NOT NULL,
    payment_type VARCHAR(30) NOT NULL,
    payment_installments INT NOT NULL DEFAULT 1 CHECK (payment_installments >= 0),
    payment_value NUMERIC(10, 2) NOT NULL CHECK (payment_value >= 0),
    PRIMARY KEY (order_id, payment_sequential)
);

COMMENT ON TABLE order_payments IS 'Payment methods and installment breakdowns per order';

-- ----------------------------------------------------------------------------
-- Table 7: ORDER_REVIEWS (Customer Feedback & Satisfaction)
-- ----------------------------------------------------------------------------
CREATE TABLE order_reviews (
    review_id VARCHAR(32) NOT NULL,
    order_id VARCHAR(32) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    review_score INT CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date TIMESTAMP,
    review_answer_timestamp TIMESTAMP,
    PRIMARY KEY (review_id, order_id)
);

COMMENT ON TABLE order_reviews IS 'Customer review ratings and feedback messages';

-- ============================================================================
-- PERFORMANCE INDEXES (Optimized for Business Intelligence & Text-to-SQL)
-- ============================================================================

CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_purchase_ts ON orders(order_purchase_timestamp);
CREATE INDEX idx_orders_status ON orders(order_status);

CREATE INDEX idx_order_items_product_id ON order_items(product_id);
CREATE INDEX idx_order_items_seller_id ON order_items(seller_id);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);

CREATE INDEX idx_products_category_eng ON products(product_category_name_english);
CREATE INDEX idx_customers_state_city ON customers(customer_state, customer_city);
CREATE INDEX idx_sellers_state_city ON sellers(seller_state, seller_city);

CREATE INDEX idx_order_payments_type ON order_payments(payment_type);
CREATE INDEX idx_order_reviews_score ON order_reviews(review_score);
