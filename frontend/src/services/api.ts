import axios from 'axios';
import {
  HealthResponse,
  KPISummaryResponse,
  MonthlyTrendItem,
  CategoryItem,
  StateItem,
  SellerItem,
  DeliverySLAItem,
  PaymentItem,
  DataQualityResponse,
  ConversationTurn,
  AskAIResponse,
  AnomalyListResponse,
  AnomalyScanRequest,
  AnomalyScanResponse,
  SQLAskResponse,
  SQLRerunRequest,
  SQLRerunResponse,
  VoiceTranscribeResponse,
  DatasetSummary,
  DatasetProfile,
  UploadDatasetResponse,
  TablePreviewResponse,
  DatasetSemanticResponse,
  UpdateDatasetSemanticRequest,
  DatasetAskResponse,
  DatasetInsightsResponse,
  DatasetDashboardResponse,
  DatasetNavigationResponse,
  WorkspaceOverviewResponse,
  WorkspaceAnalyticsResponse,
  WorkspaceGrain,
  WorkspaceTableAnalysisResponse,
  WorkspaceDataQualityResponse,
  WorkspaceAnomalyResponse,
  WorkspaceAnomalyScanResponse,
  AnomalyExplanationResponse,
  ForecastResponse,
  ScenarioBaselineResponse,
  ReportResponse
} from '../types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

export const getOwnerToken = (): string => {
  let token = localStorage.getItem('insightforge_owner_token');
  if (!token) {
    token = 'own_' + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    localStorage.setItem('insightforge_owner_token', token);
  }
  return token;
};

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 45000,
});

export const api = {
  getHealth: async (): Promise<HealthResponse> => {
    const res = await client.get<HealthResponse>('/health');
    return res.data;
  },

  getKPIs: async (): Promise<KPISummaryResponse> => {
    const res = await client.get<KPISummaryResponse>('/kpis');
    return res.data;
  },

  getRevenueTrend: async (): Promise<MonthlyTrendItem[]> => {
    const res = await client.get<MonthlyTrendItem[]>('/analytics/revenue-trend');
    return res.data;
  },

  getCategories: async (limit: number = 10): Promise<CategoryItem[]> => {
    const res = await client.get<CategoryItem[]>(`/analytics/categories?limit=${limit}`);
    return res.data;
  },

  getStates: async (): Promise<StateItem[]> => {
    const res = await client.get<StateItem[]>('/analytics/states');
    return res.data;
  },

  getSellers: async (limit: number = 10): Promise<SellerItem[]> => {
    const res = await client.get<SellerItem[]>(`/analytics/sellers?limit=${limit}`);
    return res.data;
  },

  getPayments: async (): Promise<PaymentItem[]> => {
    const res = await client.get<PaymentItem[]>('/analytics/payments');
    return res.data;
  },

  getDeliverySLA: async (): Promise<DeliverySLAItem[]> => {
    const res = await client.get<DeliverySLAItem[]>('/analytics/delivery');
    return res.data;
  },

  getDataQuality: async (): Promise<DataQualityResponse> => {
    const res = await client.get<DataQualityResponse>('/data-quality');
    return res.data;
  },

  askAI: async (question: string): Promise<AskAIResponse> => {
    const res = await client.post<AskAIResponse>('/ai/ask', { question }, { timeout: 60000 });
    return res.data;
  },

  sqlAskAI: async (question: string, history?: ConversationTurn[]): Promise<SQLAskResponse> => {
    const payload: { question: string; history?: ConversationTurn[] } = { question };
    if (history && history.length > 0) {
      payload.history = history;
    }
    const res = await client.post<SQLAskResponse>('/ai/sql-ask', payload, { timeout: 60000 });
    return res.data;
  },

  rerunOlistPin: async (payload: SQLRerunRequest): Promise<SQLRerunResponse> => {
    const res = await client.post<SQLRerunResponse>('/ai/rerun', payload, { timeout: 45000 });
    return res.data;
  },

  rerunDatasetPin: async (id: string, sql: string): Promise<SQLRerunResponse> => {
    const res = await client.post<SQLRerunResponse>(
      `/datasets/${id}/rerun`,
      { route: 'text_to_sql', sql },
      { headers: { 'X-Owner-Token': getOwnerToken() }, timeout: 45000 }
    );
    return res.data;
  },

  getAnomalies: async (metric: string = 'gross_revenue', grain: string = 'daily', severity?: string): Promise<AnomalyListResponse> => {
    let url = `/anomalies?metric=${encodeURIComponent(metric)}&grain=${encodeURIComponent(grain)}`;
    if (severity && severity !== 'all') {
      url += `&severity=${encodeURIComponent(severity)}`;
    }
    const res = await client.get<AnomalyListResponse>(url);
    return res.data;
  },

  scanAnomalies: async (params?: AnomalyScanRequest): Promise<AnomalyScanResponse> => {
    const res = await client.post<AnomalyScanResponse>('/anomalies/scan', params || {}, { timeout: 60000 });
    return res.data;
  },

  transcribeVoice: async (audioBlob: Blob, filename: string = 'recording.webm'): Promise<VoiceTranscribeResponse> => {
    const formData = new FormData();
    formData.append('file', audioBlob, filename);
    const res = await client.post<VoiceTranscribeResponse>('/voice/transcribe', formData, {
      headers: {
        'Content-Type': undefined,
      },
      timeout: 30000,
    });
    return res.data;
  },

  getDatasets: async (): Promise<DatasetSummary[]> => {
    const res = await client.get<DatasetSummary[]>('/datasets', {
      headers: { 'X-Owner-Token': getOwnerToken() },
    });
    return res.data;
  },

  getDatasetProfile: async (id: string): Promise<DatasetProfile> => {
    const res = await client.get<DatasetProfile>(`/datasets/${id}`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
    });
    return res.data;
  },

  uploadDataset: async (files: File[], datasetName?: string, shareSamples: boolean = false): Promise<UploadDatasetResponse> => {
    const formData = new FormData();
    files.forEach((f) => formData.append('files', f));
    if (datasetName && datasetName.trim()) {
      formData.append('dataset_name', datasetName.trim());
    }
    formData.append('share_samples', String(shareSamples));

    const res = await client.post<UploadDatasetResponse>('/datasets', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
        'X-Owner-Token': getOwnerToken(),
      },
      timeout: 60000,
    });

    if (res.data.owner_token) {
      localStorage.setItem('insightforge_owner_token', res.data.owner_token);
    }
    return res.data;
  },

  updateDataset: async (
    id: string,
    updates: {
      share_samples?: boolean;
      column_updates?: Array<{ table_name: string; column_name: string; role?: string; user_description?: string }>;
      confirmed_relationships?: Array<{ parent_table: string; parent_column: string; child_table: string; child_column: string; confirmed: boolean }>;
    }
  ): Promise<DatasetProfile> => {
    const res = await client.patch<DatasetProfile>(`/datasets/${id}/columns`, updates, {
      headers: { 'X-Owner-Token': getOwnerToken() },
    });
    return res.data;
  },

  previewDatasetTable: async (id: string, table: string, limit: number = 50): Promise<TablePreviewResponse> => {
    const res = await client.get<TablePreviewResponse>(`/datasets/${id}/preview`, {
      params: { table, limit },
      headers: { 'X-Owner-Token': getOwnerToken() },
    });
    return res.data;
  },

  deleteDataset: async (id: string): Promise<void> => {
    await client.delete(`/datasets/${id}`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
    });
  },

  getDatasetSemantic: async (id: string): Promise<DatasetSemanticResponse> => {
    const res = await client.get<DatasetSemanticResponse>(`/datasets/${id}/semantic`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
    });
    return res.data;
  },

  generateDatasetSemantic: async (id: string): Promise<DatasetSemanticResponse> => {
    const res = await client.post<DatasetSemanticResponse>(`/datasets/${id}/semantic/generate`, {}, {
      headers: { 'X-Owner-Token': getOwnerToken() },
    });
    return res.data;
  },

  updateDatasetSemantic: async (id: string, updates: UpdateDatasetSemanticRequest): Promise<DatasetSemanticResponse> => {
    const res = await client.patch<DatasetSemanticResponse>(`/datasets/${id}/semantic`, updates, {
      headers: { 'X-Owner-Token': getOwnerToken() },
    });
    return res.data;
  },

  askDataset: async (id: string, question: string, language: string = 'auto', history?: ConversationTurn[]): Promise<DatasetAskResponse> => {
    const payload: { question: string; language: string; history?: ConversationTurn[] } = { question, language };
    if (history && history.length > 0) {
      payload.history = history;
    }
    const res = await client.post<DatasetAskResponse>(`/datasets/${id}/ask`, payload, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      timeout: 45000,
    });
    return res.data;
  },

  getDatasetInsights: async (id: string): Promise<DatasetInsightsResponse> => {
    const res = await client.get<DatasetInsightsResponse>(`/datasets/${id}/insights`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
    });
    return res.data;
  },

  // Which sidebar sections apply to an uploaded dataset (tables + topic groups).
  getDatasetNavigation: async (id: string): Promise<DatasetNavigationResponse> => {
    const res = await client.get<DatasetNavigationResponse>(`/datasets/${id}/navigation`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      timeout: 60000,
    });
    return res.data;
  },

  // ---- Dataset-aware workspace pages (uploaded datasets only; owner token required) ----
  getDatasetOverview: async (id: string, limit = 8): Promise<WorkspaceOverviewResponse> => {
    const res = await client.get<WorkspaceOverviewResponse>(`/datasets/${id}/overview`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      params: { limit },
      timeout: 60000,
    });
    return res.data;
  },

  getDatasetAnalytics: async (
    id: string,
    opts: { metric?: string | null; grain?: WorkspaceGrain; limit?: number } = {}
  ): Promise<WorkspaceAnalyticsResponse> => {
    const params: Record<string, string | number> = { grain: opts.grain || 'monthly', limit: opts.limit ?? 8 };
    if (opts.metric) params.metric = opts.metric;
    const res = await client.get<WorkspaceAnalyticsResponse>(`/datasets/${id}/analytics`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      params,
      timeout: 60000,
    });
    return res.data;
  },

  getDatasetTableAnalysis: async (id: string, table: string): Promise<WorkspaceTableAnalysisResponse> => {
    const res = await client.get<WorkspaceTableAnalysisResponse>(`/datasets/${id}/tables/${encodeURIComponent(table)}/analysis`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      timeout: 60000,
    });
    return res.data;
  },

  getDatasetGroupAnalysis: async (id: string, group: string): Promise<WorkspaceTableAnalysisResponse> => {
    const res = await client.get<WorkspaceTableAnalysisResponse>(`/datasets/${id}/groups/${encodeURIComponent(group)}/analysis`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      timeout: 60000,
    });
    return res.data;
  },

  getDatasetDataQuality: async (id: string): Promise<WorkspaceDataQualityResponse> => {
    const res = await client.get<WorkspaceDataQualityResponse>(`/datasets/${id}/data-quality`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      timeout: 60000,
    });
    return res.data;
  },

  getDatasetAnomalies: async (
    id: string,
    opts: { metric?: string | null; grain?: 'daily' | 'weekly'; severity?: string | null } = {}
  ): Promise<WorkspaceAnomalyResponse> => {
    const params: Record<string, string> = { grain: opts.grain || 'daily' };
    if (opts.metric) params.metric = opts.metric;
    if (opts.severity) params.severity = opts.severity;
    const res = await client.get<WorkspaceAnomalyResponse>(`/datasets/${id}/anomalies`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      params,
      timeout: 90000,
    });
    return res.data;
  },

  scanDatasetAnomalies: async (id: string, grain: 'daily' | 'weekly' = 'daily'): Promise<WorkspaceAnomalyScanResponse> => {
    const res = await client.post<WorkspaceAnomalyScanResponse>(`/datasets/${id}/anomalies/scan`, null, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      params: { grain },
      timeout: 180000,
    });
    return res.data;
  },

  // One-click report. The server has a 45 s budget, so the client waits up to 60 s.
  getReport: async (datasetId: string | null): Promise<ReportResponse> => {
    const res = datasetId
      ? await client.get<ReportResponse>(`/datasets/${datasetId}/report`, {
          headers: { 'X-Owner-Token': getOwnerToken() }, params: { format: 'json' }, timeout: 60000,
        })
      : await client.get<ReportResponse>('/report', { params: { format: 'json' }, timeout: 60000 });
    return res.data;
  },

  /** Download the PDF (blob) and return it with the server-provided filename. */
  downloadReportPdf: async (datasetId: string | null): Promise<{ blob: Blob; filename: string }> => {
    const res = datasetId
      ? await client.get(`/datasets/${datasetId}/report`, {
          headers: { 'X-Owner-Token': getOwnerToken() }, params: { format: 'pdf' }, responseType: 'blob', timeout: 60000,
        })
      : await client.get('/report', { params: { format: 'pdf' }, responseType: 'blob', timeout: 60000 });
    const cd: string = res.headers['content-disposition'] || '';
    const match = /filename="?([^";]+)"?/i.exec(cd);
    return { blob: res.data as Blob, filename: match ? match[1] : 'InsightForge_Report.pdf' };
  },

  // Baseline forecast (deterministic ETS with 80% / 95% bands).
  getOlistForecast: async (
    opts: { metric?: string | null; horizon?: number; excludeAnomalies?: boolean } = {}
  ): Promise<ForecastResponse> => {
    const params: Record<string, string> = {
      horizon: String(opts.horizon ?? 3),
      exclude_anomalies: String(!!opts.excludeAnomalies),
    };
    if (opts.metric) params.metric = opts.metric;
    const res = await client.get<ForecastResponse>('/forecast', { params, timeout: 60000 });
    return res.data;
  },

  getScenarioBaseline: async (): Promise<ScenarioBaselineResponse> => {
    const res = await client.get<ScenarioBaselineResponse>('/forecast/scenario-baseline', { timeout: 30000 });
    return res.data;
  },

  getDatasetForecast: async (
    id: string, opts: { metric?: string | null; horizon?: number; excludeAnomalies?: boolean } = {}
  ): Promise<ForecastResponse> => {
    const params: Record<string, string> = {
      horizon: String(opts.horizon ?? 3),
      exclude_anomalies: String(!!opts.excludeAnomalies),
    };
    if (opts.metric) params.metric = opts.metric;
    const res = await client.get<ForecastResponse>(`/datasets/${id}/forecast`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      params,
      timeout: 60000,
    });
    return res.data;
  },

  // "Explain this anomaly" (deterministic root-cause waterfall).
  explainOlistAnomaly: async (
    metric: string, period: string, grain: 'daily' | 'weekly' = 'daily'
  ): Promise<AnomalyExplanationResponse> => {
    const res = await client.get<AnomalyExplanationResponse>('/anomalies/explain', {
      params: { metric, period, grain },
      timeout: 60000,
    });
    return res.data;
  },

  explainDatasetAnomaly: async (
    id: string, period: string, opts: { metric?: string | null; grain?: 'daily' | 'weekly' } = {}
  ): Promise<AnomalyExplanationResponse> => {
    const params: Record<string, string> = { period, grain: opts.grain || 'daily' };
    if (opts.metric) params.metric = opts.metric;
    const res = await client.get<AnomalyExplanationResponse>(`/datasets/${id}/anomalies/explain`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      params,
      timeout: 60000,
    });
    return res.data;
  },

  // Deterministic dashboard for an uploaded dataset (not available for the Olist demo).
  // Several aggregate queries against a possibly remote DB, so it gets a longer timeout.
  getDatasetDashboard: async (id: string): Promise<DatasetDashboardResponse> => {
    const res = await client.get<DatasetDashboardResponse>(`/datasets/${id}/dashboard`, {
      headers: { 'X-Owner-Token': getOwnerToken() },
      timeout: 60000,
    });
    return res.data;
  },
};

