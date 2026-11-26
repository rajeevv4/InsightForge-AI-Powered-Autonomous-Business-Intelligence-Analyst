import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import {
  DollarSign,
  ShoppingBag,
  Users,
  PackageCheck,
  TrendingUp,
  Star,
  Layers,
  Truck,
  Sparkles,
  ArrowRight
} from 'lucide-react';
import { api } from '../services/api';
import {
  KPISummaryResponse,
  MonthlyTrendItem,
  CategoryItem,
  StateItem
} from '../types/api';

import { KpiCard } from '../components/KpiCard';
import { formatMoney, formatNumber } from '../lib/format';
import { RevenueTrendChart } from '../components/RevenueTrendChart';
import { CategoryChart } from '../components/CategoryChart';
import { StateChart } from '../components/StateChart';
import { AskInsightForge } from '../components/AskInsightForge';
import { ErrorBanner } from '../components/ErrorBanner';

export const OverviewPage: React.FC = () => {
  const navigate = useNavigate();
  const outletContext = useOutletContext<{ refreshTrigger?: number }>();

  const [kpis, setKpis] = useState<KPISummaryResponse | null>(null);
  const [revenueTrend, setRevenueTrend] = useState<MonthlyTrendItem[] | null>(null);
  const [categories, setCategories] = useState<CategoryItem[] | null>(null);
  const [states, setStates] = useState<StateItem[] | null>(null);

  const [kpiLoading, setKpiLoading] = useState<boolean>(true);
  const [kpiError, setKpiError] = useState<string | null>(null);

  const [trendLoading, setTrendLoading] = useState<boolean>(true);
  const [trendError, setTrendError] = useState<string | null>(null);

  const [categoryLoading, setCategoryLoading] = useState<boolean>(true);
  const [categoryError, setCategoryError] = useState<string | null>(null);

  const [stateLoading, setStateLoading] = useState<boolean>(true);
  const [stateError, setStateError] = useState<string | null>(null);

  const loadOverviewData = useCallback(async () => {
    // 1. KPIs
    setKpiLoading(true);
    setKpiError(null);
    api.getKPIs()
      .then(setKpis)
      .catch((err) => {
        const msg = err?.response?.status === 503
          ? 'Database unavailable: The database server is currently disconnected.'
          : 'Failed to fetch executive KPIs';
        setKpiError(msg);
      })
      .finally(() => setKpiLoading(false));

    // 2. Revenue Trend
    setTrendLoading(true);
    setTrendError(null);
    api.getRevenueTrend()
      .then(setRevenueTrend)
      .catch((err) => {
        const msg = err?.response?.status === 503
          ? 'Database unavailable: The database server is currently disconnected.'
          : 'Failed to fetch revenue trend analytics';
        setTrendError(msg);
      })
      .finally(() => setTrendLoading(false));

    // 3. Categories
    setCategoryLoading(true);
    setCategoryError(null);
    api.getCategories(10)
      .then(setCategories)
      .catch((err) => {
        const msg = err?.response?.status === 503
          ? 'Database unavailable: The database server is currently disconnected.'
          : 'Failed to fetch category analytics';
        setCategoryError(msg);
      })
      .finally(() => setCategoryLoading(false));

    // 4. States
    setStateLoading(true);
    setStateError(null);
    api.getStates()
      .then(setStates)
      .catch((err) => {
        const msg = err?.response?.status === 503
          ? 'Database unavailable: The database server is currently disconnected.'
          : 'Failed to fetch state sales analytics';
        setStateError(msg);
      })
      .finally(() => setStateLoading(false));
  }, []);

  useEffect(() => {
    loadOverviewData();
  }, [loadOverviewData, outletContext?.refreshTrigger]);

  // Central formatter (same values; one R$ style across the app)
  const money = (v: number) => formatMoney(v, 'R$');
  const fmtCurr = (val: number | undefined) => (val !== undefined ? money(val) : '—');
  const fmtNum = (val: number | undefined) => (val !== undefined ? formatNumber(val) : '—');

  return (
    <div className="space-y-8 pb-12">
      {/* Welcome & Subtitle */}
      <div>
        <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
          Welcome back 👋
        </h1>
        <p className="text-xs text-slate-500 mt-1">
          Explore your business performance and discover meaningful insights from your data.
        </p>
      </div>


      {/* Hero Banner */}
      <div className="relative overflow-hidden bg-brand-gradient rounded-2xl p-6 sm:p-8 text-white shadow-glow flex flex-col md:flex-row md:items-center justify-between gap-6 animate-fade-in-up">
        <div aria-hidden="true" className="pointer-events-none absolute -right-16 -top-16 w-64 h-64 rounded-full bg-white/10 blur-2xl" />
        <div aria-hidden="true" className="pointer-events-none absolute -left-10 -bottom-20 w-56 h-56 rounded-full bg-fuchsia-400/20 blur-2xl" />
        <div className="relative space-y-2 max-w-2xl min-w-0">
          <span className="inline-flex items-center space-x-1.5 bg-white/10 text-white border border-white/20 px-3 py-1 rounded-full text-xs font-medium backdrop-blur-xs">
            <Sparkles className="w-3.5 h-3.5 text-indigo-200" />
            <span>AI-Powered Analytics Workspace</span>
          </span>
          <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight leading-snug">
            Turn Business Data into Real Insights with AI.
          </h2>
          <p className="text-xs sm:text-sm text-indigo-100/90 leading-relaxed">
            Analyze performance, discover trends, and make smarter business decisions with InsightForge.
          </p>
        </div>

        <div className="relative flex flex-col sm:flex-row gap-2 shrink-0 self-stretch sm:self-start md:self-auto">
        <button
          onClick={() => navigate('/report?autogen=1')}
          className="bg-indigo-500/30 hover:bg-indigo-500/50 text-white border border-white/30 font-bold text-xs px-5 py-3 rounded-xl transition-all flex items-center justify-center space-x-2"
        >
          <span>Generate report</span>
        </button>
        <button
          onClick={() => navigate('/ask')}
          className="bg-white hover:bg-slate-50 text-indigo-600 font-bold text-xs px-5 py-3 rounded-xl shadow-xs transition-all flex items-center justify-center space-x-2 shrink-0 self-start md:self-auto"
        >
          <span>Ask AI Assistant</span>
          <ArrowRight className="w-4 h-4" />
        </button>
        </div>
      </div>

      {/* Executive KPI Cards Grid */}
      <section className="space-y-3">
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
          Executive KPIs
        </h2>
        {kpiError ? (
          <ErrorBanner message={kpiError} onRetry={loadOverviewData} />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 stagger">
            <KpiCard
              title="Gross Revenue"
              value={fmtCurr(kpis?.gross_revenue)}
              numericValue={kpis?.gross_revenue} format={money}
              subtitle="Product + Freight Sales"
              icon={DollarSign}
              color="indigo"
            />
            <KpiCard
              title="Product Revenue"
              value={fmtCurr(kpis?.product_revenue)}
              numericValue={kpis?.product_revenue} format={money}
              subtitle="Net Sales Amount"
              icon={ShoppingBag}
              color="emerald"
            />
            <KpiCard
              title="Freight Revenue"
              value={fmtCurr(kpis?.freight_revenue)}
              numericValue={kpis?.freight_revenue} format={money}
              subtitle="Shipping Charges Collected"
              icon={Truck}
              color="amber"
            />
            <KpiCard
              title="Delivered Orders"
              value={fmtNum(kpis?.delivered_orders)}
              numericValue={kpis?.delivered_orders} format={(v) => formatNumber(Math.round(v))}
              subtitle="Fulfilled E-Commerce Orders"
              icon={PackageCheck}
              color="purple"
            />
            <KpiCard
              title="Active Customers"
              value={fmtNum(kpis?.active_customers)}
              numericValue={kpis?.active_customers} format={(v) => formatNumber(Math.round(v))}
              subtitle="Unique Purchasing Customers"
              icon={Users}
              color="blue"
            />
            <KpiCard
              title="Units Sold"
              value={fmtNum(kpis?.units_sold)}
              numericValue={kpis?.units_sold} format={(v) => formatNumber(Math.round(v))}
              subtitle="Total Purchased Line Items"
              icon={Layers}
              color="indigo"
            />
            <KpiCard
              title="Average Order Value"
              value={fmtCurr(kpis?.aov)}
              numericValue={kpis?.aov} format={money}
              subtitle="Revenue per Transaction"
              icon={TrendingUp}
              color="emerald"
            />
            <KpiCard
              title="Customer Rating (CSAT)"
              value={kpis?.csat ? `${kpis.csat.toFixed(2)} / 5.0` : '—'}
              numericValue={kpis?.csat ?? null} format={(v) => `${v.toFixed(2)} / 5.0`}
              subtitle="Mean Satisfaction Rating"
              icon={Star}
              color="amber"
            />
          </div>
        )}
      </section>

      {/* Overview Charts Grid */}
      <section className="grid grid-cols-1 xl:grid-cols-2 gap-6 lg:gap-8 min-w-0">
        <RevenueTrendChart
          data={revenueTrend}
          loading={trendLoading}
          error={trendError}
          onRetry={loadOverviewData}
        />
        <CategoryChart
          data={categories}
          loading={categoryLoading}
          error={categoryError}
          onRetry={loadOverviewData}
        />
      </section>

      {/* Regional Sales Section */}
      <section>
        <StateChart
          data={states}
          loading={stateLoading}
          error={stateError}
          onRetry={loadOverviewData}
        />
      </section>

      {/* Compact Ask InsightForge Panel */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
            Ask InsightForge AI Assistant
          </h2>
          <button
            onClick={() => navigate('/ask')}
            className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold flex items-center space-x-1"
          >
            <span>Open Dedicated View</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
        <AskInsightForge />
      </section>
    </div>
  );
};
