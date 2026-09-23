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
import { RevenueTrendChart } from '../components/RevenueTrendChart';
import { CategoryChart } from '../components/CategoryChart';
import { StateChart } from '../components/StateChart';
import { AskInsightForge } from '../components/AskInsightForge';

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
      .catch(() => setKpiError('Failed to fetch executive KPIs'))
      .finally(() => setKpiLoading(false));

    // 2. Revenue Trend
    setTrendLoading(true);
    setTrendError(null);
    api.getRevenueTrend()
      .then(setRevenueTrend)
      .catch(() => setTrendError('Failed to fetch revenue trend analytics'))
      .finally(() => setTrendLoading(false));

    // 3. Categories
    setCategoryLoading(true);
    setCategoryError(null);
    api.getCategories(10)
      .then(setCategories)
      .catch(() => setCategoryError('Failed to fetch category analytics'))
      .finally(() => setCategoryLoading(false));

    // 4. States
    setStateLoading(true);
    setStateError(null);
    api.getStates()
      .then(setStates)
      .catch(() => setStateError('Failed to fetch state sales analytics'))
      .finally(() => setStateLoading(false));
  }, []);

  useEffect(() => {
    loadOverviewData();
  }, [loadOverviewData, outletContext?.refreshTrigger]);

  const fmtCurr = (val: number | undefined) =>
    val !== undefined ? `₹${val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';
  const fmtNum = (val: number | undefined) => (val !== undefined ? val.toLocaleString() : '—');

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
      <div className="bg-gradient-to-r from-indigo-600 via-indigo-700 to-blue-600 rounded-2xl p-6 sm:p-8 text-white shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-2 max-w-2xl">
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

        <button
          onClick={() => navigate('/ask')}
          className="bg-white hover:bg-slate-50 text-indigo-600 font-bold text-xs px-5 py-3 rounded-xl shadow-xs transition-all flex items-center justify-center space-x-2 shrink-0 self-start md:self-auto"
        >
          <span>Ask AI Assistant</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      {/* Executive KPI Cards Grid */}
      <section className="space-y-3">
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
          Executive KPIs
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            title="Gross Revenue"
            value={fmtCurr(kpis?.gross_revenue)}
            subtitle="Product + Freight Sales"
            icon={DollarSign}
            color="indigo"
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
            subtitle="Shipping Charges Collected"
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
            color="blue"
          />
          <KpiCard
            title="Units Sold"
            value={fmtNum(kpis?.units_sold)}
            subtitle="Total Purchased Line Items"
            icon={Layers}
            color="indigo"
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

      {/* Overview Charts Grid */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-8">
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
