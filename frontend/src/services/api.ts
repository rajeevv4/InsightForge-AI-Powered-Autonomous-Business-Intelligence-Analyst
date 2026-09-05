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
  DataQualityResponse
} from '../types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
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
};
