import React, { useEffect, useState, useCallback } from 'react';
import {
  DollarSign,
  ShoppingBag,
  Users,
  PackageCheck,
  TrendingUp,
  Star,
  Layers,
  Truck
} from 'lucide-react';
import { api } from '../services/api';
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

import { Header } from '../components/Header';
import { KpiCard } from '../components/KpiCard';
import { RevenueTrendChart } from '../components/RevenueTrendChart';
import { CategoryChart } from '../components/CategoryChart';
import { StateChart } from '../components/StateChart';
import { SellerChart } from '../components/SellerChart';
import { PaymentChart } from '../components/PaymentChart';
import { DeliveryChart } from '../components/DeliveryChart';
import { DataQualityCard } from '../components/DataQualityCard';

export const Dashboard: React.FC = () => {
  // Global States
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [kpis, setKpis] = useState<KPISummaryResponse | null>(null);
  const [revenueTrend, setRevenueTrend] = useState<MonthlyTrendItem[] | null>(null);
  const [categories, setCategories] = useState<CategoryItem[] | null>(null);
  const [states, setStates] = useState<StateItem[] | null>(null);
  const [sellers, setSellers] = useState<SellerItem[] | null>(null);
  const [deliverySLA, setDeliverySLA] = useState<DeliverySLAItem[] | null>(null);
  const [payments, setPayments] = useState<PaymentItem[] | null>(null);
  const [dataQuality, setDataQuality] = useState<DataQualityResponse | null>(null);

  // Section Loading & Error States
  const [globalLoading, setGlobalLoading] = useState<boolean>(true);
  const [kpiLoading, setKpiLoading] = useState<boolean>(true);
  const [kpiError, setKpiError] = useState<string | null>(null);

  const [trendLoading, setTrendLoading] = useState<boolean>(true);
  const [trendError, setTrendError] = useState<string | null>(null);

  const [categoryLoading, setCategoryLoading] = useState<boolean>(true);
  const [categoryError, setCategoryError] = useState<string | null>(null);

  const [stateLoading, setStateLoading] = useState<boolean>(true);
  const [stateError, setStateError] = useState<string | null>(null);

  const [sellerLoading, setSellerLoading] = useState<boolean>(true);
  const [sellerError, setSellerError] = useState<string | null>(null);

  const [deliveryLoading, setDeliveryLoading] = useState<boolean>(true);
  const [deliveryError, setDeliveryError] = useState<string | null>(null);

  const [paymentLoading, setPaymentLoading] = useState<boolean>(true);
  const [paymentError, setPaymentError] = useState<string | null>(null);

  const [dqLoading, setDqLoading] = useState<boolean>(true);
  const [dqError, setDqError] = useState<string | null>(null);

  // Fetch All Data
  const loadDashboardData = useCallback(async () => {
    setGlobalLoading(true);

    // 1. Health
    api.getHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: 'degraded', database: 'disconnected', service: 'InsightForge', version: '0.1.0' }));

    // 2. KPIs
    setKpiLoading(true);
    setKpiError(null);
    api.getKPIs()
      .then((data) => {
        setKpis(data);
        setKpiLoading(false);
      })
      .catch((err) => {
        setKpiError('Failed to fetch canonical KPIs');
        setKpiLoading(false);
      });

    // 3. Revenue Trend
    setTrendLoading(true);
    setTrendError(null);
    api.getRevenueTrend()
      .then((data) => {
        setRevenueTrend(data);
        setTrendLoading(false);
      })
      .catch(() => {
        setTrendError('Failed to fetch revenue trend analytics');
        setTrendLoading(false);
      });

    // 4. Categories
    setCategoryLoading(true);
    setCategoryError(null);
    api.getCategories(10)
      .then((data) => {
        setCategories(data);
        setCategoryLoading(false);
      })
      .catch(() => {
        setCategoryError('Failed to fetch product category analytics');
        setCategoryLoading(false);
      });

    // 5. States
    setStateLoading(true);
    setStateError(null);
    api.getStates()
      .then((data) => {
        setStates(data);
        setStateLoading(false);
      })
      .catch(() => {
        setStateError('Failed to fetch state analytics');
        setStateLoading(false);
      });

    // 6. Sellers
    setSellerLoading(true);
    setSellerError(null);
    api.getSellers(10)
      .then((data) => {
        setSellers(data);
        setSellerLoading(false);
      })
      .catch(() => {
        setSellerError('Failed to fetch seller analytics');
        setSellerLoading(false);
      });

    // 7. Delivery SLA
    setDeliveryLoading(true);
    setDeliveryError(null);
    api.getDeliverySLA()
      .then((data) => {
        setDeliverySLA(data);
        setDeliveryLoading(false);
      })
      .catch(() => {
        setDeliveryError('Failed to fetch delivery SLA analytics');
        setDeliveryLoading(false);
      });

    // 8. Payments
    setPaymentLoading(true);
    setPaymentError(null);
    api.getPayments()
      .then((data) => {
        setPayments(data);
        setPaymentLoading(false);
      })
      .catch(() => {
        setPaymentError('Failed to fetch payment analytics');
        setPaymentLoading(false);
      });

    // 9. Data Quality
    setDqLoading(true);
    setDqError(null);
    api.getDataQuality()
      .then((data) => {
        setDataQuality(data);
        setDqLoading(false);
      })
      .catch(() => {
        setDqError('Failed to fetch data quality report');
        setDqLoading(false);
      });

    setGlobalLoading(false);
  }, []);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  // Format Helper
  const fmtCurr = (val: number | undefined) =>
    val !== undefined ? `R$ ${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';
  const fmtNum = (val: number | undefined) => (val !== undefined ? val.toLocaleString() : '—');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-16">
      
      {/* Header Bar */}
      <Header health={health} loading={globalLoading} onRefresh={loadDashboardData} />

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 space-y-8">
        
        {/* Executive KPI Cards Grid */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-white tracking-tight">Executive Business KPIs</h2>
            <span className="text-xs text-slate-400 font-mono">Delivered Orders Scope</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard
              title="Gross Revenue"
              value={fmtCurr(kpis?.gross_revenue)}
              subtitle="Product + Freight Sales"
              icon={DollarSign}
              color="blue"
            />
            <KpiCard
              title="Product Revenue"
              value={fmtCurr(kpis?.product_revenue)}
              subtitle="Net Sales Amount"
              icon={ShoppingBag}
              color="emerald"
            />
            <KpiCard
              title="Freight Revenue"
              value={fmtCurr(kpis?.freight_revenue)}
              subtitle="Total Freight Charges"
              icon={Truck}
              color="amber"
            />
            <KpiCard
              title="Delivered Orders"
              value={fmtNum(kpis?.delivered_orders)}
              subtitle="Fulfilled E-Commerce Orders"
              icon={PackageCheck}
              color="purple"
            />

            <KpiCard
              title="Active Customers"
              value={fmtNum(kpis?.active_customers)}
              subtitle="Unique Purchasing Customers"
              icon={Users}
              color="slate"
            />
            <KpiCard
              title="Units Sold"
              value={fmtNum(kpis?.units_sold)}
              subtitle="Total Purchased Line Items"
              icon={Layers}
              color="blue"
            />
            <KpiCard
              title="Average Order Value"
              value={fmtCurr(kpis?.aov)}
              subtitle="Revenue per Transaction"
              icon={TrendingUp}
              color="emerald"
            />
            <KpiCard
              title="Customer Rating (CSAT)"
              value={kpis?.csat ? `${kpis.csat.toFixed(2)} / 5.0` : '—'}
              subtitle="Mean Satisfaction Rating"
              icon={Star}
              color="amber"
            />
          </div>
        </section>

        {/* Section 1: Monthly Revenue Trend & Category Analysis */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <RevenueTrendChart
            data={revenueTrend}
            loading={trendLoading}
            error={trendError}
            onRetry={loadDashboardData}
          />
          <CategoryChart
            data={categories}
            loading={categoryLoading}
            error={categoryError}
            onRetry={loadDashboardData}
          />
        </section>

        {/* Section 2: Regional States & Top Sellers */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <StateChart
            data={states}
            loading={stateLoading}
            error={stateError}
            onRetry={loadDashboardData}
          />
          <SellerChart
            data={sellers}
            loading={sellerLoading}
            error={sellerError}
            onRetry={loadDashboardData}
          />
        </section>

        {/* Section 3: Delivery SLA & Payment Breakdown */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <DeliveryChart
            data={deliverySLA}
            loading={deliveryLoading}
            error={deliveryError}
            onRetry={loadDashboardData}
          />
          <PaymentChart
            data={payments}
            loading={paymentLoading}
            error={paymentError}
            onRetry={loadDashboardData}
          />
        </section>

        {/* Section 4: Data Quality Audit Panel */}
        <section>
          <DataQualityCard
            data={dataQuality}
            loading={dqLoading}
            error={dqError}
            onRetry={loadDashboardData}
          />
        </section>

      </main>
    </div>
  );
};
