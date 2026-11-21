export interface HealthResponse {
  status: string;
  database: string;
  data_source: 'postgres' | 'fixture';
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

export interface AskAIRequest {
  question: string;
}

export interface AIEvidence {
  source: string;
  intent: string;
  metric: string;
  data: any;
}

export interface AskAIResponse {
  question: string;
  intent: string;
  confidence: number;
  reason: string;
  answer: string;
  evidence?: AIEvidence | null;
  rephrase_suggested?: boolean;
}

export interface AnomalyItem {
  metric: string;
  dimension: string;
  period: string;
  observed: number;
  expected: number;
  deviation_score: number;
  severity: 'low' | 'medium' | 'high';
  direction: 'spike' | 'drop';
  method: string;
  known_event_candidate?: string | null;
}

export interface AnomalyTimeSeriesPoint {
  period: string;
  observed: number;
  expected?: number | null;
  is_anomaly: boolean;
  severity?: string | null;
  deviation_score?: number | null;
  known_event?: string | null;
}

export interface AnomalyListResponse {
  metric: string;
  grain: string;
  total_anomalies: number;
  anomalies: AnomalyItem[];
  time_series: AnomalyTimeSeriesPoint[];
}

export interface AnomalyScanRequest {
  grain?: string;
  metrics?: string[];
  methods?: string[];
}

export interface AnomalyScanResponse {
  scan_status: string;
  grain: string;
  metrics_analyzed: string[];
  total_anomalies_detected: number;
  anomalies_by_severity: Record<string, number>;
  anomalies: AnomalyItem[];
}

