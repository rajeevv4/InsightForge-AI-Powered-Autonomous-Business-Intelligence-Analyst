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
  AskAIResponse,
  AnomalyListResponse,
  AnomalyScanRequest,
  AnomalyScanResponse,
  SQLAskResponse,
  VoiceTranscribeResponse,
  DatasetSummary,
  DatasetProfile,
  UploadDatasetResponse,
  TablePreviewResponse,
  DatasetSemanticResponse,
  UpdateDatasetSemanticRequest,
  DatasetAskResponse,
  DatasetInsightsResponse
} from '../types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

const getOwnerToken = (): string => {
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
  timeout: 15000,
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
    const res = await client.post<AskAIResponse>('/ai/ask', { question });
    return res.data;
  },

  sqlAskAI: async (question: string): Promise<SQLAskResponse> => {
    const res = await client.post<SQLAskResponse>('/ai/sql-ask', { question });
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
    const res = await client.post<AnomalyScanResponse>('/anomalies/scan', params || {});
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

  askDataset: async (id: string, question: string, language: string = 'auto'): Promise<DatasetAskResponse> => {
    const res = await client.post<DatasetAskResponse>(`/datasets/${id}/ask`, { question, language }, {
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
};

