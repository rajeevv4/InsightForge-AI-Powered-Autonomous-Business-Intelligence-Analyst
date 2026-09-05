export interface HealthResponse {
  status: string;
  database: string;
  service: string;
  version: string;
}

export interface KPISummaryResponse {
  product_revenue: number;
  freight_revenue: number;
  gross_revenue: number;
  delivered_orders: number;
  active_customers: number;
  units_sold: number;
  aov: number;
  csat: number;
}

export interface MonthlyTrendItem {
  month: string;
  total_orders: number;
  total_items_sold: number;
  product_revenue: number;
  freight_revenue: number;
  gross_revenue: number;
  aov: number;
  prev_month_revenue?: number | null;
  mom_revenue_growth_pct?: number | null;
  mom_order_growth_pct?: number | null;
  mom_aov_growth_pct?: number | null;
}

export interface CategoryItem {
  category: string;
  total_orders: number;
  units_sold: number;
  total_revenue: number;
  avg_item_price: number;
  avg_review_score?: number | null;
  revenue_share_percent: number;
}

export interface StateItem {
  state: string;
  active_customers: number;
  total_orders: number;
  total_product_revenue: number;
  total_freight_revenue: number;
  total_gross_revenue: number;
  avg_freight_cost: number;
  revenue_share_percent: number;
}

export interface SellerItem {
  seller_id: string;
  seller_city: string;
  seller_state: string;
  total_orders_fulfilled: number;
  units_sold: number;
  unique_products_offered: number;
  total_sales_revenue: number;
  avg_seller_review_score?: number | null;
}

export interface DeliverySLAItem {
  delivery_status: string;
  order_count: number;
  percentage: number;
  avg_actual_delivery_days?: number | null;
  avg_estimated_delivery_days?: number | null;
  avg_delay_days?: number | null;
}

export interface PaymentItem {
  payment_type: string;
  order_count: number;
  total_payment_value: number;
  avg_payment_amount: number;
  avg_installments: number;
}

export interface DataQualityResponse {
  audit_status: string;
  table_row_counts: Record<string, number>;
  missing_value_summary: Record<string, number>;
  primary_key_uniqueness: string;
  foreign_key_integrity: string;
  domain_bounds_status: string;
  order_status_breakdown: Record<string, number>;
  join_safety_status: string;
  anomalies_flagged: string[];
}
