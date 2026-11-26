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

export interface ConversationTurn {
  question: string;
  sql?: string | null;
  intent?: string | null;
}

export interface AskAIRequest {
  question: string;
  history?: ConversationTurn[];
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
  intent?: string | null;
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

export interface SQLRerunRequest {
  route: 'intent' | 'text_to_sql';
  intent?: string | null;
  sql?: string | null;
}

export interface SQLRerunResponse {
  rows: Record<string, any>[];
  columns: string[];
  row_count: number;
  sql?: string | null;
  execution_time_ms: number;
}

export interface PinnedCardSpec {
  id: string;
  question: string;
  route: 'intent' | 'text_to_sql';
  intent?: string | null;
  sql?: string | null;
  dataset_id: string;
  dataset_name: string;
  chart_spec: 'bar' | 'line' | 'pie' | 'table';
  pinned_at: string;
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

// Mirrors backend/app/schemas/anomaly.py::AnomalyScanResponse
export interface AnomalyScanResponse {
  scan_id: string;
  status: string;
  anomalies_detected: number;
  high_severity_count: number;
  scanned_metrics: string[];
  anomalies: AnomalyItem[];
  slice_outliers?: AnomalyItem[];
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
  warning?: string; // legacy parser-warning shape stored by older uploads
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



// ---------------------------------------------------------------------------
// Dataset Dashboard (uploaded datasets only)
// Mirrors backend/app/schemas/dataset_semantic.py::DatasetDashboardResponse
// ---------------------------------------------------------------------------
export interface DashboardKPI {
  label: string;
  table: string;
  column: string | null;
  aggregation: 'COUNT' | 'SUM' | 'AVG' | 'MIN' | 'MAX' | string;
  value: number | null;
  error: string | null;
}

export interface DashboardTrend {
  title: string;
  table: string;
  measure_column: string;
  measure_label: string;
  aggregation: string;
  time_column: string;
  points: { period: string; value: number | null }[];
}

export interface DashboardBreakdownItem {
  label: string;
  value: number | null;
  row_count: number;
}

export interface DashboardBreakdown {
  title: string;
  dimension_table: string;
  dimension_column: string;
  dimension_label: string;
  measure_label: string;
  aggregation: string;
  join_path: string | null;
  items: DashboardBreakdownItem[];
  other_value: number | null;
  other_groups: number;
  total_value: number | null;
  truncated: boolean;
}

export interface DashboardSkippedBreakdown {
  dimension: string;
  reason: string;
}

export interface DashboardQualityTable {
  table: string;
  row_count: number;
  findings: { type: string; column?: string | null; severity: string; message: string }[];
}

export interface DashboardAnomalyItem {
  period: string;
  observed: number;
  expected: number;
  deviation_score: number;
  severity: string;
  direction: string;
}

export interface DashboardAnomalies {
  measure_label: string | null;
  method: string;
  items: DashboardAnomalyItem[];
  note: string | null;
}

export interface DatasetDashboardResponse {
  dataset_id: string;
  dataset_name: string;
  primary_measure: string | null;
  kpis: DashboardKPI[] | null;
  trend: DashboardTrend | null;
  breakdowns: DashboardBreakdown[] | null;
  skipped_breakdowns: DashboardSkippedBreakdown[];
  data_quality: DashboardQualityTable[] | null;
  anomalies: DashboardAnomalies | null;
  section_errors: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Dataset navigation (uploaded datasets only)
// Mirrors backend/app/services/dataset_navigation_service.py::DatasetNavigationResponse
// ---------------------------------------------------------------------------
export interface DatasetNavigationItem {
  key: string; // 'overview' | 'datasets' | 'ask' | 'analytics' | 'table:<name>' | 'geography' | 'sellers' | 'payments' | 'delivery' | 'data_quality' | 'anomalies'
  label: string;
  path: string;
  kind: 'core' | 'table' | 'group';
  table: string | null;
  matched_columns: string[];
}

export interface DatasetNavigationResponse {
  dataset_id: string;
  dataset_name: string;
  items: DatasetNavigationItem[];
  hidden: { key: string; label: string; reason: string }[];
  semantic_model_used: boolean;
}

// ---------------------------------------------------------------------------
// Dataset-aware workspace pages (uploaded datasets only)
// Mirrors backend/app/schemas/dataset_workspace.py
// ---------------------------------------------------------------------------
export interface MetricOption {
  key: string; // 'table.column' or 'table.*'
  label: string;
  table: string;
  column: string | null;
  aggregation: string;
}

export interface WorkspaceSectionBase {
  dataset_id: string;
  dataset_name: string;
  section_errors: Record<string, string>;
  cached: boolean;
  generated_at: string;
}

export interface WorkspaceOverviewResponse extends WorkspaceSectionBase {
  primary_measure: string | null;
  kpis: DashboardKPI[] | null;
  trend: DashboardTrend | null;
  breakdowns: DashboardBreakdown[] | null;
  skipped_breakdowns: DashboardSkippedBreakdown[];
  quality_summary: { tables: number; findings: number; by_severity: Record<string, number> } | null;
}

export type WorkspaceGrain = 'daily' | 'weekly' | 'monthly';

export interface WorkspaceAnalyticsResponse extends WorkspaceSectionBase {
  metrics: MetricOption[];
  metric: string | null;
  grain: WorkspaceGrain;
  available_grains: WorkspaceGrain[];
  time_column: string | null;
  trend: DashboardTrend | null;
  breakdowns: DashboardBreakdown[] | null;
  skipped_breakdowns: DashboardSkippedBreakdown[];
}

export interface ColumnSummary {
  name: string;
  pg_type: string;
  role: string;
  null_pct: number;
  distinct_count: number;
  min_val: string | null;
  max_val: string | null;
}

export interface WorkspaceTableAnalysisResponse extends WorkspaceSectionBase {
  table: string;
  group: string | null;
  row_count: number;
  columns: ColumnSummary[];
  matched_columns: string[];
  kpis: DashboardKPI[] | null;
  primary_measure: string | null;
  trend: DashboardTrend | null;
  breakdowns: DashboardBreakdown[] | null;
  skipped_breakdowns: DashboardSkippedBreakdown[];
}

export interface DataQualityCheck {
  check: 'primary_key' | 'foreign_key' | 'negative_values' | 'future_dates' | 'missing_values' | 'join_safety' | 'table_scan' | string;
  table: string;
  column: string | null;
  status: 'PASS' | 'WARN' | 'FAIL' | 'SKIPPED';
  value: number | null;
  detail: string;
}

export interface WorkspaceDataQualityResponse extends WorkspaceSectionBase {
  audit_status: string;
  table_row_counts: Record<string, number>;
  missing_value_summary: Record<string, number>;
  primary_key_uniqueness: string;
  foreign_key_integrity: string;
  domain_bounds_status: string;
  order_status_breakdown: Record<string, number>;
  join_safety_status: string;
  anomalies_flagged: string[];
  checks: DataQualityCheck[];
  status_column: string | null;
}

export interface WorkspaceAnomalyResponse extends WorkspaceSectionBase {
  total_anomalies: number;
  grain: 'daily' | 'weekly';
  metric: string;
  anomalies: (AnomalyItem & { classification?: string | null })[];
  time_series: (AnomalyTimeSeriesPoint & { direction?: string | null })[];
  slice_outliers: AnomalyItem[];
  metrics: MetricOption[];
  methods_run: string[];
  notes: string[];
}

export interface WorkspaceAnomalyScanResponse {
  dataset_id: string;
  scan_id: string;
  status: string;
  anomalies_detected: number;
  high_severity_count: number;
  scanned_metrics: string[];
  anomalies: AnomalyItem[];
  slice_outliers: AnomalyItem[];
}

// ---------------------------------------------------------------------------
// "Explain this anomaly" (root-cause waterfall). All numbers and sentences are
// computed deterministically on the server (no LLM).
// ---------------------------------------------------------------------------
export interface ExplainHeadline {
  observed: number;
  expected: number;
  change_abs: number;
  change_pct?: number | null;
  direction: 'spike' | 'drop' | string;
  source: 'detector' | 'time_series_baseline' | 'trailing_baseline' | string;
  method?: string | null;
  severity?: string | null;
  sentence: string;
}

export interface ExplainDriver {
  label: string;
  observed: number;
  expected: number;
  contribution: number;
  share_of_change_pct?: number | null;
  sentence: string;
}

export interface WaterfallStep {
  name: string;
  kind: 'total' | 'up' | 'down' | 'other' | string;
  start: number;
  end: number;
  value: number;
}

export interface ExplainDimension {
  key: string;
  label: string;
  explanatory_power: number;
  mix_shift: number;
  rank_score: number;
  groups: number;
  drivers: ExplainDriver[];
  other_contribution: number;
  other_groups: number;
  waterfall: WaterfallStep[];
  summary: string;
  join_path?: string | null;
}

export interface ExplainTopDriver {
  dimension: string;
  label: string;
  contribution: number;
  share_of_change_pct?: number | null;
  sentence: string;
}

export interface VolumeValue {
  volume_label: string;
  value_label: string;
  volume_observed: number;
  volume_expected: number;
  value_observed?: number | null;
  value_expected?: number | null;
  volume_effect: number;
  value_effect: number;
  dominant: 'volume' | 'value' | string;
  sentences: string[];
}

export interface AnomalyExplanationResponse {
  dataset_id: string;
  dataset_name: string;
  metric: string;
  metric_label: string;
  period: string;
  grain: 'daily' | 'weekly' | string;
  currency?: string | null;
  unit: 'currency' | 'count' | 'percent' | 'score' | 'number' | string;
  additive: boolean;
  baseline_window: string;
  baseline_periods: number;
  headline?: ExplainHeadline | null;
  dimensions: ExplainDimension[];
  top_drivers: ExplainTopDriver[];
  volume_value?: VolumeValue | null;
  skipped_dimensions: { dimension: string; reason: string }[];
  notes: string[];
  section_errors: Record<string, string>;
  generated_at?: string | null;
  cached: boolean;
}

/** Where an anomaly came from: the built-in Olist demo or an uploaded dataset. */
export type ExplainSource = { kind: 'olist' } | { kind: 'dataset'; datasetId: string };

// ---------------------------------------------------------------------------
// Baseline forecast (deterministic ETS, no LLM)
// ---------------------------------------------------------------------------
export interface ForecastPoint {
  period: string;
  expected: number;
  lower_80: number;
  upper_80: number;
  lower_95: number;
  upper_95: number;
}

export interface ForecastResponse {
  dataset_id: string;
  dataset_name: string;
  metric?: string | null;
  metric_label?: string | null;
  metrics: { key: string; label: string; aggregation: string }[];
  currency?: string | null;
  horizon: number;
  exclude_anomalies: boolean;
  excluded_days: number;
  status: 'ok' | 'refused' | string;
  reason?: string | null;
  reliability?: 'Good' | 'Fair' | 'Weak' | null | string;
  model?: string | null;
  model_kind?: 'monthly' | 'daily' | null | string;
  training_window?: string | null;
  history: { period: string; value: number; raw_value?: number | null }[];
  forecast: ForecastPoint[];
  backtest?: {
    holdout: string;
    mape?: number | null;
    naive_mape?: number | null;
    naive_method: string;
    beats_naive: boolean;
    points: { period: string; actual: number; forecast: number; naive: number }[];
  } | null;
  notes: string[];
  disclaimer: string;
  section_errors: Record<string, string>;
  generated_at?: string | null;
  cached: boolean;
}

// ---------------------------------------------------------------------------
// One-click report (deterministic templates; PDF via the same endpoint, format=pdf)
// ---------------------------------------------------------------------------
export interface ReportResponse {
  dataset_id: string;
  dataset_name: string;
  is_demo: boolean;
  currency?: string | null;
  generated_at: string;
  period?: string | null;
  row_counts: Record<string, number>;
  total_rows?: number | null;
  summary?: string[] | null;
  kpis?: { label: string; value?: number | null; display: string }[] | null;
  trend?: { title: string; points: { period: string; value: number }[] } | null;
  breakdowns?: {
    title: string;
    items: { label: string; value?: number | null; display: string; share_pct?: number | null }[];
    other_groups: number;
    other_display?: string | null;
    total_value?: number | null;
    total_line?: string | null;
  }[] | null;
  anomalies?: {
    period: string; metric_label: string; direction: string; severity: string; method: string;
    observed_display: string; expected_display: string; driver_sentence: string;
  }[] | null;
  anomaly_count?: number | null;
  forecast?: {
    metric_label: string; status: string; reliability?: string | null; reason?: string | null; model?: string | null;
    training_window?: string | null; mape?: number | null; naive_mape?: number | null;
    points: { period: string; expected: number; lower_80: number; upper_80: number; expected_display: string; range_display: string }[];
    disclaimer: string;
  } | null;
  data_quality?: { check: string; status: string; detail: string }[] | null;
  caveats: string[];
  methodology: string[];
  section_errors: Record<string, string>;
  budget_seconds: number;
  elapsed_seconds: number;
  cached: boolean;
}
