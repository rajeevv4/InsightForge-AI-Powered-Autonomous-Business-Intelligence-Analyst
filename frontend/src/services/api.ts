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
  VoiceTranscribeResponse
} from '../types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

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
        'Content-Type': 'multipart/form-data',
      },
      timeout: 30000,
    });
    return res.data;
  },
};

