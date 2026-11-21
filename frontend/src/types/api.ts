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
  language?: 'en' | 'hi' | 'hinglish' | string;
  rephrase_suggested?: boolean;
}

export interface SQLAskResponse {
  question: string;
  route: 'intent' | 'text_to_sql';
  sql?: string | null;
  explanation: string;
  assumptions?: string[] | null;
  rows?: Record<string, any>[] | null;
  columns?: string[] | null;
  row_count: number;
  language?: 'en' | 'hi' | 'hinglish' | string;
  grounding_verified: boolean;
  suggested_chart?: 'bar' | 'line' | 'pie' | 'table' | null;
  error?: string | null;
}

export interface VoiceTranscribeResponse {
  text: string;
  detected_language: 'hi' | 'en' | 'hinglish' | string;
  confidence: number;
  duration_est_s?: number | null;
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

export interface ColumnProfile {
  id?: string;
  original_name: string;
  safe_name: string;
  pg_type: string;
  role: 'id' | 'datetime' | 'measure' | 'dimension' | 'boolean' | 'free_text';
  null_pct: number;
  distinct_count: number;
  min_val?: string | null;
  max_val?: string | null;
  stats: Record<string, any>;
  user_description?: string | null;
}

export interface QualityFinding {
  type: string;
  column?: string;
  severity: 'low' | 'medium' | 'high';
  message: string;
  description?: string;
}

export interface TableProfile {
  id?: string;
  original_name: string;
  safe_name: string;
  row_count: number;
  column_count: number;
  candidate_pk?: string | null;
  candidate_time_column?: string | null;
  quality_findings: QualityFinding[];
  columns: ColumnProfile[];
}

export interface RelationshipProfile {
  id?: string;
  parent_table: string;
  parent_column: string;
  child_table: string;
  child_column: string;
  cardinality: '1:1' | '1:N';
  confidence: number;
  confirmed: boolean;
}

export interface DatasetSummary {
  id: string;
  name: string;
  schema_name: string;
  status: string;
  share_samples: boolean;
  table_count: number;
  total_rows: number;
  size_bytes: number;
  created_at?: string | null;
  expires_at?: string | null;
  is_demo: boolean;
}

export interface DatasetProfile {
  id: string;
  name: string;
  schema_name: string;
  status: string;
  share_samples: boolean;
  source_files: string[];
  size_bytes: number;
  created_at?: string | null;
  expires_at?: string | null;
  is_demo: boolean;
  tables: TableProfile[];
  relationships: RelationshipProfile[];
}

export interface UploadDatasetResponse {
  dataset_id: string;
  name: string;
  schema_name: string;
  owner_token?: string | null;
  tables_count: number;
  total_rows: number;
  expires_at?: string | null;
  message: string;
}

export interface TablePreviewResponse {
  dataset_id: string;
  table_name: string;
  total_rows: number;
  preview_rows_count: number;
  columns: string[];
  rows: Record<string, any>[];
}

export interface MeasureDefinition {
  name: string;
  safe_name: string;
  table: string;
  column?: string | null;
  aggregation: string;
  formula?: string | null;
  description?: string | null;
  synonyms: string[];
}

export interface DimensionDefinition {
  name: string;
  safe_name: string;
  table: string;
  column: string;
  data_type: string;
  description?: string | null;
  synonyms: string[];
}

export interface TimeColumnDefinition {
  name: string;
  safe_name: string;
  table: string;
  column: string;
  data_type: string;
}

export interface CandidateKeyDefinition {
  table: string;
  column: string;
}

export interface RelationshipDefinition {
  parent_table: string;
  parent_column: string;
  child_table: string;
  child_column: string;
  cardinality: string;
  confirmed: boolean;
}

export interface SemanticModel {
  dataset_id: string;
  dataset_name: string;
  measures: MeasureDefinition[];
  dimensions: DimensionDefinition[];
  time_columns: TimeColumnDefinition[];
  candidate_keys: CandidateKeyDefinition[];
  relationships: RelationshipDefinition[];
  user_notes?: string | null;
}

export interface DatasetSemanticResponse {
  dataset_id: string;
  status: 'draft' | 'confirmed';
  semantic_model: SemanticModel;
  starter_questions: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface UpdateDatasetSemanticRequest {
  status?: string;
  measures?: MeasureDefinition[];
  dimensions?: DimensionDefinition[];
  relationships?: RelationshipDefinition[];
  starter_questions?: string[];
  user_notes?: string;
}

export interface DatasetAskResponse {
  question: string;
  sql: string;
  explanation: string;
  suggested_chart: 'bar' | 'line' | 'pie' | 'table';
  assumptions: string[];
  data_rows: Record<string, any>[];
  columns: string[];
  privacy_badge: 'AI sees: schema only' | 'AI sees: schema + data';
  execution_time_ms: number;
  row_count: number;
}

export interface InsightChartSpec {
  title: string;
  chart_type: 'line' | 'bar' | 'pie' | 'table';
  sql: string;
  x_axis: string;
  y_axis: string;
  data: Record<string, any>[];
}

export interface DatasetInsightsResponse {
  dataset_id: string;
  time_trend?: InsightChartSpec | null;
  top_n?: InsightChartSpec | null;
  distribution?: InsightChartSpec | null;
  anomalies: Array<{
    period: string;
    metric: string;
    actual_value: number;
    expected_value: number;
    deviation_pct: number;
    severity: string;
    label: string;
    direction: string;
  }>;
}


